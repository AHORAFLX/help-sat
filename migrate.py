"""
migrate.py
==========
Equivalente Python de test.ps1.
Genera la estructura: docs \\ CATEGORIA \\ CARPETA \\ ARTICULO.md
Motor Markdown Anti-Aplastamiento: Inyecta y repara espacios para un formato perfecto.

Dependencias:
    pip install pyodbc requests html2text
"""

import argparse
from collections import defaultdict
import html as html_lib
import json
import os
import re
import sys
import tempfile
import unicodedata
import urllib.parse
from pathlib import Path
from typing import Optional

import html2text
import pyodbc
import requests
from bs4 import BeautifulSoup

from generation_state import (
    finalize_generation_state,
    get_state_path,
    load_generation_state,
    record_generated_article,
    reset_run_state,
    should_generate_article,
)
from migrate_author_bridge import run_author_articles

# ---------------------------------------------------------------------------
# Configuración de sesión HTTP global (reutiliza conexiones TCP)
# ---------------------------------------------------------------------------
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

# ---------------------------------------------------------------------------
# Helpers generales
# ---------------------------------------------------------------------------

def get_safe_filename(name: str, fallback: str, max_length: int = 100) -> str:
    """Genera un nombre de fichero seguro eliminando caracteres problemáticos."""
    if not name or not name.strip():
        return fallback
    safe = re.sub(r'[<>:"/\\|?*\n\r]', '-', name)
    safe = safe[:max_length].strip().rstrip('.')
    return safe if safe.strip() else fallback


def normalize_article_key(text: str) -> str:
    """Normaliza un título de artículo para usarlo como clave de búsqueda difusa."""
    if not text or not text.strip():
        return ""
    decoded = urllib.parse.unquote(text)
    # Eliminar marcas diacríticas (acentos)
    normalized = unicodedata.normalize('NFD', decoded)
    result = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
    result = result.lower()
    result = re.sub(r'[^a-z0-9]+', ' ', result)
    result = re.sub(r'\s+', ' ', result).strip()
    return result


def build_article_output_plan(
    article_rows: list,
    docs_folder: Path,
    dic_categorias: dict[str, str],
    dic_carpetas: dict[str, str],
    selected_ids: Optional[list[str]] = None,
) -> dict[str, Path]:
    """Calcula rutas de salida evitando colisiones de nombre dentro de la misma carpeta."""
    grouped: dict[str, list[tuple[str, str, str, str, str]]] = defaultdict(list)

    for row in article_rows:
        try:
            raw = row[0]
            if not raw or not str(raw).strip():
                continue

            articulo = json.loads(raw)
            art_id = articulo.get('Id') or articulo.get('id')
            if art_id is None:
                continue

            cat_id = str(articulo.get('CategoryId') or articulo.get('category_id') or '')
            if selected_ids and cat_id not in selected_ids:
                continue

            folder_id = str(articulo.get('FolderId') or articulo.get('folder_id') or '')
            title = articulo.get('Title') or articulo.get('title') or ''

            cat_name = dic_categorias.get(cat_id, 'Categoria_Desconocida')
            folder_name = dic_carpetas.get(folder_id, 'Carpeta_Desconocida')
            clean_title = get_safe_filename(title, f'Articulo_{art_id}')
            base_key = f'{cat_name}/{folder_name}/{clean_title}.md'
            grouped[base_key].append((str(art_id), title, clean_title, cat_name, folder_name))
        except Exception:
            continue

    planned_paths: dict[str, Path] = {}
    for entries in grouped.values():
        has_collision = len(entries) > 1
        for art_id, _title, clean_title, cat_name, folder_name in entries:
            if has_collision:
                filename = get_safe_filename(f'{clean_title} [{art_id}]', f'Articulo_{art_id}') + '.md'
            else:
                filename = clean_title + '.md'
            planned_paths[art_id] = docs_folder / cat_name / folder_name / filename

    return planned_paths


def load_env_file(env_file: Path) -> None:
    """Carga variables de entorno desde un archivo .env sencillo."""
    if not env_file.exists():
        return

    for raw_line in env_file.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue

        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip()

        if not key:
            continue

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        os.environ.setdefault(key, value)


def resolve_connection_string(cli_value: Optional[str], env_file: Path) -> str:
    """Resuelve la connection string desde CLI o variables de entorno."""
    if cli_value and cli_value.strip():
        return cli_value.strip()

    load_env_file(env_file)

    for env_key in (
        'AUTHOR_ARTICLES_CONNECTION_STRING',
        'DB_CONNECTION_STRING',
        'SQLSERVER_CONNECTION_STRING',
    ):
        env_value = os.environ.get(env_key, '').strip()
        if env_value:
            return env_value

    raise RuntimeError(
        'No se ha encontrado la connection string. '
        'Pásala por --connection-string o define AUTHOR_ARTICLES_CONNECTION_STRING '
        'en el archivo .env.'
    )


# ---------------------------------------------------------------------------
# Motor de conversión HTML → Markdown
# ---------------------------------------------------------------------------

# Compilar las regex de SQL una sola vez (rendimiento)
_SQL_START = re.compile(
    r'^\s*(IF\s+NOT\s+EXISTS|SELECT\s+|UPDATE\s+[\[\w]|INSERT\s+INTO|DELETE\s+FROM'
    r'|DECLARE\s+@|BEGIN\b|CREATE\s+(?:TABLE|PROC|VIEW|FUNCTION)|ALTER\s+(?:TABLE|PROC|VIEW|FUNCTION)'
    r'|USE\s+\[|EXEC\s+\w|SET\s+(?:ANSI|NOCOUNT|@)|\bDim\s+\w+\s+As\b|\bSet\s+\w+\s*=)',
    re.IGNORECASE
)
_SQL_CONTINUE = re.compile(
    r'^\s*(--|@@|@\w+|AND\b|OR\b|WHERE\b|FROM\b|JOIN\b|ON\b|LEFT\b|RIGHT\b|INNER\b'
    r'|GROUP\b|ORDER\b|HAVING\b|VALUES\b|SET\b|END\b|IF\b|ELSE\b|CASE\b|WHEN\b|THEN\b'
    r'|AS\b|GO\b|\s*\[\w+\]\s*|PRINT\b|EXEC\b|DECLARE\b|\(|\)|\w+\s*=|\'\'|\bWith\b'
    r'|\bEnd\s+With\b|\.\w+)',
    re.IGNORECASE
)

FLAG = re.IGNORECASE | re.DOTALL


def _detect_code_lang(code: str) -> str:
    """Detecta el lenguaje de un bloque de código para el hint de la valla."""
    if re.search(r'\b(SELECT|UPDATE|INSERT|DELETE|DECLARE|IF\s+NOT\s+EXISTS|BEGIN|CREATE|ALTER|EXEC|SET)\b', code, re.IGNORECASE):
        return 'sql'
    if re.search(r'\b(function|var|let|const|=>|console\.log)\b', code, re.IGNORECASE):
        return 'javascript'
    if re.search(r'\b(using\s+System|public\s+class|private|void|string|int)\b', code, re.IGNORECASE):
        return 'csharp'
    if re.search(r'\b(Dim\s+\w+|Set\s+\w+\s*=|End\s+With|\.\w+\s*=)\b', code, re.IGNORECASE):
        return 'vb'
    if re.search(r'(?m)^\s*<[a-z]+[ >]', code):
        return 'html'
    return ''


def convert_html_to_markdown(html: str) -> str:
    """Convierte HTML a Markdown usando html2text + post-procesado propio."""
    if not html or not html.strip():
        return ""


    # ── Configurar html2text ──────────────────────────────────────────────
    h = html2text.HTML2Text()
    h.ignore_links  = False   # conservar enlaces
    h.ignore_images = False   # conservar imágenes
    h.body_width    = 0       # sin saltos de línea automáticos
    h.protect_links = False
    h.wrap_links    = False
    h.unicode_snob  = True    # usar caracteres Unicode reales
    h.mark_code     = False   # dejar que html2text use sus propias vallas

    md = h.handle(html)

    # ── PASO B: HEURÍSTICA PARA SQL REZAGADO EN TEXTO PLANO ──────────────
    # Solo se aplica a líneas fuera de bloques de código ya creados por html2text.
    lines = md.split('\n')
    new_lines: list[str] = []
    current_block: list[str] = []
    in_sql    = False
    in_fence  = False          # dentro de un bloque ``` ya existente
    sql_counter = [1]
    sql_map: dict[str, str] = {}

    for line in lines:
        trimmed = line.strip()

        # Detectar entrada/salida de bloques de código existentes
        if trimmed.startswith('```'):
            in_fence = not in_fence
            if in_sql and not in_fence:
                # Flush del bloque SQL antes de entrar en una valla
                sql_content = '\n'.join(current_block).strip()
                if sql_content:
                    token = f'%%SQLBLK_{sql_counter[0]}%%'
                    sql_map[token] = sql_content
                    sql_counter[0] += 1
                    new_lines.extend(['', token, ''])
                in_sql = False
                current_block.clear()
            new_lines.append(line)
            continue

        if in_fence:
            new_lines.append(line)
            continue

        if not in_sql:
            if _SQL_START.match(trimmed):
                in_sql = True
                current_block.clear()
                current_block.append(line)
            else:
                new_lines.append(line)
        else:
            if trimmed == '':
                current_block.append(line)
            else:
                is_normal_text = (
                    bool(re.match(r'^[A-ZÁÉÍÓÚ¿¡][^\n]{15,}?[.!?]$', trimmed))
                    and not _SQL_CONTINUE.match(trimmed)
                )
                long_non_sql = (
                    len(trimmed) > 80
                    and not _SQL_CONTINUE.match(trimmed)
                    and not re.search(r'[=><+\-*]', trimmed)
                )
                if is_normal_text or long_non_sql:
                    sql_content = '\n'.join(current_block).strip()
                    if sql_content:
                        token = f'%%SQLBLK_{sql_counter[0]}%%'
                        sql_map[token] = sql_content
                        sql_counter[0] += 1
                        new_lines.extend(['', token, ''])
                    in_sql = False
                    current_block.clear()
                    new_lines.append(line)
                else:
                    current_block.append(line)

    if in_sql:
        sql_content = '\n'.join(current_block).strip()
        if sql_content:
            token = f'%%SQLBLK_{sql_counter[0]}%%'
            sql_map[token] = sql_content
            sql_counter[0] += 1
            new_lines.extend(['', token, ''])

    md = '\n'.join(new_lines)

    # ── Añadir hints de lenguaje a bloques ``` sin hint ───────────────────
    def _add_lang_hint(m: re.Match) -> str:
        existing_hint = m.group(1).strip()
        content       = m.group(2)
        if existing_hint:          # ya tiene hint, respetar
            return m.group(0)
        lang = _detect_code_lang(content)
        return f'```{lang}\n{content}```'

    md = re.sub(r'```(\w*)\n(.*?)```', _add_lang_hint, md, flags=re.DOTALL)

    # ── Restaurar bloques SQL detectados por heurística ───────────────────
    for token, content in sql_map.items():
        lang = _detect_code_lang(content)
        md = md.replace(token, f'\n\n```{lang}\n{content}\n```\n\n')

    # ── Limpieza de artefactos Freshdesk ──────────────────────────────────
    # Imagen rota del tipo [* ](url)
    md = re.sub(r'\[\s*\*\s*\]\((https?://[^\s)]+)\)', r'![]( \1)', md)
    # Imagen envuelta en enlace de Freshdesk/S3 → quitar enlace exterior
    md = re.sub(
        r'\[(!\[[^\]]*\]\([^)]+\))\]\((https?://[^\s)]*?(?:amazonaws|freshdesk)[^\s)]*)\)',
        r'\1', md
    )

    # ── Normalización final ───────────────────────────────────────────────
    md = re.sub(r'\*\*\s*\*\*', '', md)
    md = re.sub(r'\*\*\s+\*\*', ' ', md)
    md = re.sub(r'\*\s*\*', '', md)
    md = re.sub(r'\n{3,}', '\n\n', md)

    return md.strip()


# ---------------------------------------------------------------------------
# Descarga de imágenes
# ---------------------------------------------------------------------------

TABLE_HTML_RX = re.compile(r'(?is)<table\b[^>]*>.*?</table>')
HTML_IMG_SRC_RX = re.compile(r'(?is)(<img\b[^>]*\bsrc=["\'])(https?://[^"\']+)(["\'][^>]*>)')


def protect_html_tables(html: str) -> tuple[str, dict[str, str]]:
    """
    Sustituye tablas HTML por tokens para preservar su estructura real
    durante la conversión a Markdown.
    """
    table_map: dict[str, str] = {}
    counter = 1

    def repl(match: re.Match) -> str:
        nonlocal counter
        token = f'%%HTMLTABLE_{counter}%%'
        counter += 1
        table_map[token] = match.group(0)
        return f'\n\n{token}\n\n'

    protected = TABLE_HTML_RX.sub(repl, html or '')
    return protected, table_map


def protect_youtube_embeds(html: str) -> tuple[str, dict[str, str]]:
    """
    Protege iframes de YouTube para restaurarlos luego como HTML embebido.
    Evita que html2text los elimine y reutiliza el CSS `.video-wrapper`.
    """
    if not html or 'youtu' not in html.lower():
        return html, {}

    soup = BeautifulSoup(html, 'html.parser')
    embed_map: dict[str, str] = {}
    counter = 1

    def is_youtube_src(src: str) -> bool:
        src = (src or '').lower()
        return any(host in src for host in ('youtube.com', 'youtu.be', 'youtube-nocookie.com'))

    def pick_replace_node(iframe_tag):
        node = iframe_tag
        if node.parent and node.parent.name == 'span':
            parent_text = node.parent.get_text(' ', strip=True)
            if not parent_text:
                node = node.parent
        if node.parent and node.parent.name in ('p', 'div'):
            parent = node.parent
            clone = BeautifulSoup(str(parent), 'html.parser')
            for br in clone.find_all('br'):
                br.extract()
            text = clone.get_text(' ', strip=True)
            if not text:
                node = parent
        return node

    for iframe in soup.find_all('iframe'):
        src = html_lib.unescape((iframe.get('src') or '').strip())
        if not is_youtube_src(src):
            continue

        if src.startswith('//'):
            src = f'https:{src}'

        token = f'%%YOUTUBE_EMBED_{counter}%%'
        counter += 1
        safe_src = html_lib.escape(src, quote=True)
        embed_map[token] = (
            '<div class="video-wrapper">'
            f'<iframe src="{safe_src}" '
            'title="YouTube video player" '
            'loading="lazy" '
            'referrerpolicy="strict-origin-when-cross-origin" '
            'allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" '
            'allowfullscreen></iframe>'
            '</div>'
        )

        replace_node = pick_replace_node(iframe)
        replace_node.replace_with(token)

    return str(soup), embed_map


def mkdocs_html_image_src(docs_root: Path, md_file_path: Path, local_path: Path) -> str:
    """
    Calcula una ruta relativa compatible con MkDocs cuando use_directory_urls=True.
    """
    md_rel = md_file_path.relative_to(docs_root)
    target_rel = local_path.relative_to(docs_root)

    output_parts = list(md_rel.parts[:-1])
    if md_file_path.stem.lower() != 'index':
        output_parts.append(md_file_path.stem)

    up = '../' * len(output_parts)
    return f'{up}{target_rel.as_posix()}'


def download_images_in_html_fragment(
    html_fragment: str,
    docs_root: Path,
    md_file_path: Path,
    images_out_dir: Path,
    article_title: str = "",
    broken_images_log: list = None,
) -> str:
    """
    Descarga imágenes referenciadas desde HTML crudo preservado y actualiza
    sus src a rutas locales.
    """
    if broken_images_log is None:
        broken_images_log = []
    images_out_dir.mkdir(parents=True, exist_ok=True)

    downloaded: dict[str, str] = {}
    matches = list(HTML_IMG_SRC_RX.finditer(html_fragment))

    for m in reversed(matches):
        prefix = m.group(1)
        url = (m.group(2) or '').strip()
        suffix = m.group(3)

        url = re.sub(r'[\r\n\t]', '', url).strip()
        url = url.replace(' ', '%20')
        url = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', url)

        if not url:
            continue

        if url in downloaded:
            rel = downloaded[url]
            html_fragment = html_fragment[:m.start()] + f'{prefix}{rel}{suffix}' + html_fragment[m.end():]
            continue

        try:
            parsed = urllib.parse.urlparse(url)
            if 'wiki.ahora.es' in parsed.netloc.lower():
                broken_images_log.append((url, article_title))
                print(f'    [INFO] Saltando imagen de wiki.ahora.es: {url}')
                continue

            img_filename = Path(parsed.path).name or 'image'
            safe_name = get_safe_filename(img_filename, 'image')
            local_path = images_out_dir / safe_name

            if local_path.exists():
                rel = mkdocs_html_image_src(docs_root, md_file_path, local_path)
                downloaded[url] = rel
                html_fragment = html_fragment[:m.start()] + f'{prefix}{rel}{suffix}' + html_fragment[m.end():]
                print(f'    [OK] Imagen reutilizada: {local_path.name}')
                continue

            resp = SESSION.get(url, timeout=30, stream=True)
            resp.raise_for_status()

            ext = Path(safe_name).suffix
            if not ext or len(ext) > 5 or not re.match(r'\.(png|jpg|jpeg|gif|webp)', ext, re.IGNORECASE):
                ct = resp.headers.get('Content-Type', '')
                ext_map = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/gif': '.gif', 'image/webp': '.webp'}
                ext = next((v for k, v in ext_map.items() if k in ct), '.jpg')
                safe_name = safe_name + ext

            local_path = images_out_dir / safe_name
            if local_path.exists():
                rel = mkdocs_html_image_src(docs_root, md_file_path, local_path)
                downloaded[url] = rel
                html_fragment = html_fragment[:m.start()] + f'{prefix}{rel}{suffix}' + html_fragment[m.end():]
                print(f'    [OK] Imagen HTML reutilizada: {local_path.name}')
                continue

            i = 1
            stem = Path(safe_name).stem
            suf = Path(safe_name).suffix
            while local_path.exists():
                local_path = images_out_dir / f'{stem}_{i}{suf}'
                i += 1

            with open(local_path, 'wb') as f:
                for chunk in resp.iter_content(8192):
                    f.write(chunk)

            rel = mkdocs_html_image_src(docs_root, md_file_path, local_path)
            downloaded[url] = rel
            html_fragment = html_fragment[:m.start()] + f'{prefix}{rel}{suffix}' + html_fragment[m.end():]
            print(f'    [OK] Imagen HTML descargada: {local_path.name}')

        except Exception as e:
            print(f'    [WARN] Fallo al descargar imagen HTML: {url} — {e}', file=sys.stderr)

    return html_fragment


def preprocess_reference_html(article_title: str, html: str) -> str:
    """
    Prepara HTML de documentación de API para que Implementación / Descripción /
    Ejemplo de uso se conviertan en bloques de código cuando realmente son código.
    """
    if not html:
        return html

    def normalize_heading_hierarchy(raw_html: str) -> str:
        soup = BeautifulSoup(raw_html, 'html.parser')

        # Eliminar título duplicado si el HTML empieza con el mismo título del artículo.
        first_tag = soup.find(['h1', 'h2', 'p'])
        if first_tag:
            text = first_tag.get_text(strip=True).lower()
            if article_title and article_title.lower().strip() == text:
                first_tag.decompose()

        # Convertir encabezados largos o con pinta de párrafo en texto normal.
        for tag in soup.find_all(['h1', 'h2', 'h3']):
            full_text = tag.get_text(strip=True)
            if len(full_text) > 100 or full_text.endswith('.') or full_text.endswith(':'):
                tag.name = 'p'

        # Ajustar niveles para que MkDocs genere bien la tabla de contenido.
        for h2 in soup.find_all('h2'):
            h2.name = 'h3'
        for h1 in soup.find_all('h1'):
            h1.name = 'h2'

        return str(soup)

    html = normalize_heading_hierarchy(html)

    def clean_paragraph_block(block: str) -> str:
        parts = re.findall(r"(?is)<p[^>]*>(.*?)</p>", block)
        lines: list[str] = []
        for part in parts:
            part = re.sub(r"(?is)<br\s*/?>", "\n", part)
            part = re.sub(r"<[^>]+>", "", part)
            part = html_lib.unescape(part).replace("\xa0", " ")
            for line in part.splitlines():
                line = line.strip()
                if line:
                    lines.append(line)
        return "\n".join(lines).strip()

    def wrap_implementation(m: re.Match) -> str:
        heading, body, tail = m.groups()
        cleaned = clean_paragraph_block(body)
        meaningful = [ln for ln in cleaned.splitlines() if ln.strip()]
        looks_code = any(
            re.search(
                r"^(Public|Private|Friend)?\s*(Function|Sub|Property)\b|^Dim\b|^Set\b|^If\b|^End\b|^\w+\s*=|^\w+\.",
                ln,
                re.IGNORECASE,
            )
            for ln in meaningful
        )
        return f"{heading}<pre>{cleaned}</pre>{tail}" if cleaned and looks_code else f"{heading}{body}{tail}"

    def wrap_description_signatures(m: re.Match) -> str:
        heading, body, tail = m.groups()
        nodes = re.findall(r"(?is)<table\b[^>]*>.*?</table>|<p[^>]*>.*?</p>", body)
        prose_parts: list[str] = []
        code_parts: list[str] = []
        code_started = False
        for node in nodes:
            if re.match(r"(?is)^<table\b", node):
                if code_started and code_parts:
                    prose_parts.append(f'<pre>{"\\n".join(code_parts)}</pre>')
                    code_parts = []
                    code_started = False
                prose_parts.append(node)
                continue

            plain = html_lib.unescape(re.sub(r"<[^>]+>", "", node)).replace("\xa0", " ").strip()
            if not plain:
                continue
            looks_signature = bool(re.match(r"^(Public|Private|Friend)?\s*(Function|Sub|Property)\b", plain, re.IGNORECASE))
            if looks_signature or code_started:
                code_started = True
                code_parts.append(plain)
            else:
                prose_parts.append(f'<p>{plain}</p>')
        prose_html = ''.join(prose_parts)
        code_html = f'<pre>{"\\n".join(code_parts)}</pre>' if code_parts else ''
        return f"{heading}{prose_html}{code_html}{tail}"

    def wrap_example(m: re.Match) -> str:
        heading, body = m.groups()
        cleaned = clean_paragraph_block(body)
        meaningful = [ln for ln in cleaned.splitlines() if ln.strip()]
        code_hits = sum(
            1
            for ln in meaningful
            if re.search(
                r"^(Public|Private|Friend)?\s*(Function|Sub|Property)\b|^Dim\b|^Set\b|^If\b|^End\b|^\w+\s*=|^\w+\.|^'.*|^MsgBox\b",
                ln,
                re.IGNORECASE,
            )
        )
        return f"{heading}<pre>{cleaned}</pre>" if cleaned and code_hits >= max(2, min(3, len(meaningful))) else f"{heading}{body}"

    html = re.sub(
        r"(?is)(<p[^>]*>\s*Implementaci\S*n:\s*</p>)(.*?)(<p[^>]*>\s*Descripci\S*n:\s*</p>)",
        wrap_implementation,
        html,
        count=1,
    )
    html = re.sub(
        r"(?is)(<p[^>]*>\s*Descripci\S*n:\s*</p>)(.*?)(<p[^>]*>\s*Ejemplo de uso[^<]*</p>|$)",
        wrap_description_signatures,
        html,
        count=1,
    )
    html = re.sub(
        r"(?is)(<p[^>]*>\s*Ejemplo de uso[^<]*</p>)(.*)$",
        wrap_example,
        html,
        count=1,
    )
    return html


def apply_known_article_html_fixes(article_id: str, html: str) -> str:
    """
    Ajustes HTML quirúrgicos para artículos concretos antes de pasar por html2text.
    """
    aid = str(article_id or "").strip()
    if not html:
        return html

    if aid == "154000238352":
        soup = BeautifulSoup(html, 'html.parser')
        for pre in soup.find_all('pre'):
            code_tag = pre.find('code')
            if not code_tag:
                continue

            classes = list(code_tag.get('class', []))
            lang = ''
            for cls in classes:
                cls = str(cls)
                if cls.startswith('language-'):
                    lang = cls.split('-', 1)[1].strip().lower()
                    break

            text = pre.get_text('\n')
            text = html_lib.unescape(text).replace('\r\n', '\n').replace('\r', '\n')
            text = re.sub(r'\n{3,}', '\n\n', text).strip('\n')

            clean_code = soup.new_tag('code')
            if not lang:
                stripped = text.strip()
                if (stripped.startswith('{') or stripped.startswith('[')) and re.search(r'"\w+"\s*:', stripped):
                    lang = 'json'
                elif re.search(r"^\s*[\[\]\w]+\s*(=|<>|>|<|>=|<=)\s*['\w(]", text, re.IGNORECASE | re.MULTILINE) or re.search(r'\b(AND|OR|IN|LIKE|IS\s+NULL|IS\s+NOT\s+NULL)\b', text, re.IGNORECASE):
                    lang = 'sql'

            if lang:
                clean_code['class'] = [f'language-{lang}']
            clean_code.string = text
            pre.clear()
            pre.append(clean_code)

        return str(soup)

    return html


def protect_known_article_pre_blocks(article_id: str, html: str) -> tuple[str, dict[str, str]]:
    """
    Protege bloques <pre> solo en artículos con HTML especialmente problemático.
    """
    aid = str(article_id or "").strip()
    if aid != "154000238352" or not html or '<pre' not in html.lower():
        return html, {}

    soup = BeautifulSoup(html, 'html.parser')
    pre_map: dict[str, str] = {}
    counter = 1

    for pre in soup.find_all('pre'):
        code_tag = pre.find('code')
        classes = list(code_tag.get('class', [])) if code_tag else []
        lang = ''
        for cls in classes:
            cls = str(cls)
            if cls.startswith('language-'):
                lang = cls.split('-', 1)[1].strip().lower()
                break

        text = pre.get_text('\n')
        text = html_lib.unescape(text).replace('\r\n', '\n').replace('\r', '\n')
        text = re.sub(r'\n{3,}', '\n\n', text).strip('\n')
        if not text.strip():
            continue

        if not lang:
            stripped = text.strip()
            if (stripped.startswith('{') or stripped.startswith('[')) and re.search(r'"\w+"\s*:', stripped):
                lang = 'json'
            elif re.search(r"^\s*[\[\]\w]+\s*(=|<>|>|<|>=|<=)\s*['\w(]", text, re.IGNORECASE | re.MULTILINE) or re.search(r'\b(AND|OR|IN|LIKE|IS\s+NULL|IS\s+NOT\s+NULL)\b', text, re.IGNORECASE):
                lang = 'sql'
            else:
                lang = _detect_code_lang(text)

        token = f'%%KNOWNPRE_{counter}%%'
        counter += 1
        pre_map[token] = f'\n\n```{lang}\n{text}\n```\n\n'
        pre.replace_with(token)

    return str(soup), pre_map


def apply_known_article_fixes(article_id: str, md_text: str) -> str:
    """
    Ajustes quirúrgicos mínimos para artículos que aún necesitan una ayuda extra.
    """
    aid = str(article_id or "").strip()
    if not md_text:
        return md_text

    if aid in {"154000130036", "154000130021"}:
        def _clean_code_block(block: str) -> str:
            lines = [html_lib.unescape(line).strip() for line in block.splitlines()]
            lines = [line for line in lines if line and not line.strip().startswith("```")]
            return "\n".join(lines).strip()

        signature_rx = re.compile(
            r"((?:Implementaci\S*n):\n+)(.*?)(\n+(?:Descripci\S*n):)",
            re.IGNORECASE | re.DOTALL,
        )
        usage_rx = re.compile(
            r"((?:Ejemplo de uso):\n+)(.*)$",
            re.IGNORECASE | re.DOTALL,
        )

        def _wrap_signature(m: re.Match) -> str:
            prefix, code_block, suffix = m.groups()
            cleaned = _clean_code_block(code_block)
            return f"{prefix}```vb\n{cleaned}\n```\n\n{suffix}"

        def _wrap_usage(m: re.Match) -> str:
            prefix, code_block = m.groups()
            cleaned = _clean_code_block(code_block)
            return f"{prefix}```vb\n{cleaned}\n```"

        md_text = signature_rx.sub(_wrap_signature, md_text, count=1)
        md_text = usage_rx.sub(_wrap_usage, md_text, count=1)
        md_text = re.sub(r"\n{3,}", "\n\n", md_text).strip()

    if aid == "154000238352":
        md_text = re.sub(
            r'("TemplateId":\s*")\s*([A-Z0-9_]+)\s*(")',
            r'\1\2\3',
            md_text,
        )
        md_text = md_text.replace(
            "```vb\nStatusId = 'ON' AND Priority = 'HIGH'\n```",
            "```sql\nStatusId = 'ON' AND Priority = 'HIGH'\n```",
        )

    if aid == "154000130232":
        md_text = re.sub(r'(?m)^(#{1,6})\s+__\s+(.*)$', r'\1 \2', md_text)
        md_text = re.sub(r'(?m)^####\s*$', '', md_text)

    return md_text


def repair_vb_reference_markdown(article_title: str, md_text: str) -> str:
    """
    Reetiqueta fences VB y, en casos de documentación tipo API, reagrupa
    firmas/ejemplos VB que hayan quedado como texto plano.
    """
    title = str(article_title or "").strip()
    if not md_text:
        return md_text

    def retag_vb_like_fences(text: str) -> str:
        def repl(match: re.Match) -> str:
            lang = match.group(1)
            body = match.group(2).replace("\\n", "\n")
            if re.search(
                r"^(Public|Private|Friend)?\s*(Function|Sub|Property)\b|^Dim\b|^Set\b|^If\b|^End\b|^\w+\s*=|^\w+\.|^'.*|^MsgBox\b",
                body,
                re.IGNORECASE | re.MULTILINE,
            ):
                lang = "vb"
            return f"```{lang}\n{body}\n```"

        return re.sub(r"```(\w*)\n(.*?)\n```", repl, text, flags=re.DOTALL)

    md_text = retag_vb_like_fences(md_text)

    def unwrap_short_fences(text: str) -> str:
        def repl(match: re.Match) -> str:
            body = match.group(1)
            meaningful = [ln for ln in body.splitlines() if ln.strip()]
            return body.strip("\n") if len(meaningful) <= 12 else match.group(0)
        return re.sub(r"```vb\n(.*?)\n```", repl, text, flags=re.DOTALL | re.IGNORECASE)

    def is_code_like(line: str) -> bool:
        stripped = line.strip()
        if not stripped:
            return False
        patterns = [
            r"^(Public|Private|Friend)?\s*(Function|Sub|Property)\b",
            r"^End\s+(Function|Sub|Property|If|With|Select)\b",
            r"^(Optional\s+)?[A-Za-z_]\w*\s+As\s+[A-Za-z_]",
            r"^As\s+[A-Za-z_]",
            r"^Dim\s+\w+",
            r"^Set\s+\w+\s*=",
            r"^(If|ElseIf|Else|While|Wend|Do|Loop|For|Next)\b",
            r"^Exit\s+(Sub|Function|Do|For)\b",
            r"^MsgBox\b",
            r"^[A-Za-z_]\w*\s*=",
            r"^[A-Za-z_]\w*\.",
            r'^".*',
            r"^'.*",
        ]
        return any(re.search(pattern, stripped, re.IGNORECASE) for pattern in patterns)

    def flush_run(run: list[str], out: list[str]) -> None:
        if not run:
            return
        trimmed = [ln.strip() for ln in run if ln.strip()]
        code_hits = sum(1 for ln in trimmed if is_code_like(ln))
        strong_start = bool(trimmed) and is_code_like(trimmed[0])
        if trimmed and (strong_start or code_hits >= max(2, (len(trimmed) + 1) // 2)):
            out.append("```vb")
            out.extend(trimmed)
            out.append("```")
        else:
            out.extend(run)
        run.clear()

    text = unwrap_short_fences(md_text) if title in {"GeneraApunte", "Crea Copia Doc"} else md_text
    lines = text.splitlines()
    out: list[str] = []
    run: list[str] = []
    in_fence = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            flush_run(run, out)
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue
        if is_code_like(line) or (run and not stripped):
            run.append(line)
            continue
        flush_run(run, out)
        out.append(line)

    flush_run(run, out)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def convert_article_html_to_markdown(
    html: str,
    docs_root: Path,
    md_file_path: Path,
    images_out_dir: Path,
    article_title: str = "",
    article_id: str = "",
    broken_images_log: list = None,
) -> str:
    """
    Envoltorio modular sobre convert_html_to_markdown.
    Conserva tablas HTML como HTML crudo y reutiliza la descarga
    de imágenes Markdown ya existente. Si la tabla contiene imágenes,
    también actualiza sus src a local.
    """
    if broken_images_log is None:
        broken_images_log = []

    html = apply_known_article_html_fixes(article_id, html)
    html, known_pre_map = protect_known_article_pre_blocks(article_id, html)
    html, youtube_embed_map = protect_youtube_embeds(html)
    html = preprocess_reference_html(article_title, html)
    protected_html, table_map = protect_html_tables(html)
    md_content = convert_html_to_markdown(protected_html)
    md_content = download_images_from_markdown(
        md_content,
        md_file_path,
        images_out_dir,
        article_title,
        broken_images_log,
    )

    for token, table_html in table_map.items():
        local_table_html = download_images_in_html_fragment(
            table_html,
            docs_root,
            md_file_path,
            images_out_dir,
            article_title,
            broken_images_log,
        )
        md_content = md_content.replace(token, f'\n\n{local_table_html}\n\n')

    md_content = fix_ordered_list_artifacts_fast(md_content)
    for token, content in known_pre_map.items():
        md_content = md_content.replace(token, content)
    for token, content in youtube_embed_map.items():
        md_content = md_content.replace(token, f'\n\n{content}\n\n')
    md_content = normalize_markdown_list_spacing(md_content)
    md_content = apply_known_article_fixes(article_id, md_content)
    md_content = repair_vb_reference_markdown(article_title, md_content)
    md_content = apply_known_article_fixes(article_id, md_content)
    return re.sub(r'\n{3,}', '\n\n', md_content).strip()


def fix_ordered_list_artifacts(md_content: str) -> str:
    """
    Corrige listas ordenadas rotas por html2text cuando el HTML original usa
    <li> separados para texto, imagen, caption o espacios en blanco.
    """
    lines = md_content.splitlines()
    out: list[str] = []

    hidden_count = 0
    last_visible_indent: Optional[str] = None
    last_visible_exists = False
    last_was_embedded_media = False

    item_rx = re.compile(r'^(\s*)(\d+)\.\s*(.*)$')
    image_only_rx = re.compile(r'^\s*!\[[^\]]*\]\([^)]+\)\s*$')
    blankish_rx = re.compile(r'^(?:\s| |&nbsp;)*$')
    caption_rx = re.compile(r'^\s*_.*_\s*$')

    def continuation_indent(base: Optional[str]) -> str:
        return (base or '') + '   '

    for line in lines:
        m = item_rx.match(line)
        if m:
            indent, num_s, body = m.groups()
            body = body or ''

            if image_only_rx.match(body) and last_visible_exists:
                out.append(f'{continuation_indent(last_visible_indent)}{body.strip()}')
                hidden_count += 1
                last_was_embedded_media = True
                continue

            if blankish_rx.match(body) and last_visible_exists:
                hidden_count += 1
                last_was_embedded_media = True
                continue

            try:
                num = int(num_s)
            except ValueError:
                num = 1
            visible_num = max(1, num - hidden_count)
            out.append(f'{indent}{visible_num}. {body}')
            last_visible_indent = indent
            last_visible_exists = True
            last_was_embedded_media = False
            continue

        if caption_rx.match(line) and last_was_embedded_media and last_visible_exists:
            out.append(f'{continuation_indent(last_visible_indent)}{line.strip()}')
            continue

        if blankish_rx.match(line):
            out.append(line)
            continue

        # Al salir de una lista o entrar en texto normal, reseteamos estado
        hidden_count = 0
        last_visible_indent = None
        last_visible_exists = False
        last_was_embedded_media = False
        out.append(line)

    return '\n'.join(out)


def fix_ordered_list_artifacts_fast(md_content: str) -> str:
    """
    Versión lineal y más barata del postproceso de listas ordenadas.
    Evita regexs de "línea vacía" sobre cada línea para no atascarse en artículos largos.
    """
    lines = md_content.splitlines()
    out: list[str] = []

    hidden_count = 0
    last_visible_indent: Optional[str] = None
    last_visible_exists = False
    last_was_embedded_media = False

    item_rx = re.compile(r'^(\s*)(\d+)\.\s*(.*)$')
    image_only_rx = re.compile(r'^\s*!\[[^\]]*\]\([^)]+\)\s*$')
    caption_rx = re.compile(r'^\s*_.*_\s*$')

    def continuation_indent(base: Optional[str]) -> str:
        return (base or '') + '   '

    def is_blankish(text: str) -> bool:
        if not text:
            return True
        normalized = text.replace('&nbsp;', ' ').replace('\xa0', ' ').replace('Â\xa0', ' ').replace('Â ', ' ')
        return normalized.strip() == ''

    for line in lines:
        m = item_rx.match(line)
        if m:
            indent, num_s, body = m.groups()
            body = body or ''

            if image_only_rx.match(body) and last_visible_exists:
                out.append(f'{continuation_indent(last_visible_indent)}{body.strip()}')
                hidden_count += 1
                last_was_embedded_media = True
                continue

            if is_blankish(body) and last_visible_exists:
                hidden_count += 1
                last_was_embedded_media = True
                continue

            try:
                num = int(num_s)
            except ValueError:
                num = 1
            visible_num = max(1, num - hidden_count)
            out.append(f'{indent}{visible_num}. {body}')
            last_visible_indent = indent
            last_visible_exists = True
            last_was_embedded_media = False
            continue

        if caption_rx.match(line) and last_was_embedded_media and last_visible_exists:
            out.append(f'{continuation_indent(last_visible_indent)}{line.strip()}')
            continue

        if is_blankish(line):
            out.append(line)
            continue

        hidden_count = 0
        last_visible_indent = None
        last_visible_exists = False
        last_was_embedded_media = False
        out.append(line)

    return '\n'.join(out)


def normalize_markdown_list_spacing(md_content: str) -> str:
    """
    Corrige viñetas mal formadas tipo "  *Texto" -> "  * Texto"
    y elimina restos de formato vacío como líneas "__".
    """
    if not md_content:
        return md_content

    md_content = re.sub(r'(?m)^(\s{2,})\*(\S)', r'\1* \2', md_content)
    md_content = re.sub(r'(?m)^\s*__\s*$\n?', '', md_content)
    return md_content


def download_images_from_markdown(
    md_content: str,
    md_file_path: Path,
    images_out_dir: Path,
    article_title: str = "",
    broken_images_log: list = None
) -> str:
    """Descarga imágenes remotas y reemplaza URLs por rutas relativas locales."""
    if broken_images_log is None:
        broken_images_log = []
    images_out_dir.mkdir(parents=True, exist_ok=True)

    pattern = re.compile(r'!\[(.*?)\]\((https?://[^\s)]+)\)')
    downloaded: dict[str, str] = {}

    # Iterar sobre todos los matches (de atrás hacia adelante en el string)
    matches = list(pattern.finditer(md_content))

    for m in reversed(matches):
        full_match = m.group(0)
        alt_text   = m.group(1)
        url        = m.group(2)

        # Sanitizar URL
        url = re.sub(r'[\r\n\t]', '', url).strip()
        url = url.replace(' ', '%20')
        url = re.sub(r'[\u200b\u200c\u200d\ufeff]', '', url)

        if url in downloaded:
            rel = downloaded[url]
            md_content = md_content[:m.start()] + f'![{alt_text}]({rel})' + md_content[m.end():]
            continue

        try:
            parsed = urllib.parse.urlparse(url)
            if 'wiki.ahora.es' in parsed.netloc.lower():
                broken_images_log.append((url, article_title))
                print(f'    [INFO] Saltando imagen de wiki.ahora.es: {url}')
                continue
                
            img_filename = Path(parsed.path).name or 'image'
            safe_name = get_safe_filename(img_filename, 'image')
            local_path = images_out_dir / safe_name

            if local_path.exists():
                rel = _relative_posix(md_file_path.parent, local_path)
                downloaded[url] = rel
                md_content = md_content[:m.start()] + f'![{alt_text}]({rel})' + md_content[m.end():]
                print(f'    [OK] Imagen reutilizada: {local_path.name}')
                continue

            resp = SESSION.get(url, timeout=30, stream=True)
            resp.raise_for_status()

            # Deducir extensión si no la tiene
            ext = Path(safe_name).suffix
            if not ext or len(ext) > 5 or not re.match(r'\.(png|jpg|jpeg|gif|webp)', ext, re.IGNORECASE):
                ct = resp.headers.get('Content-Type', '')
                ext_map = {'image/jpeg': '.jpg', 'image/png': '.png', 'image/gif': '.gif', 'image/webp': '.webp'}
                ext = next((v for k, v in ext_map.items() if k in ct), '.jpg')
                safe_name = safe_name + ext

            local_path = images_out_dir / safe_name
            if local_path.exists():
                rel = _relative_posix(md_file_path.parent, local_path)
                downloaded[url] = rel
                md_content = md_content[:m.start()] + f'![{alt_text}]({rel})' + md_content[m.end():]
                print(f'    [OK] Imagen reutilizada: {local_path.name}')
                continue

            # Evitar sobreescribir
            i = 1
            stem = Path(safe_name).stem
            suf  = Path(safe_name).suffix
            while local_path.exists():
                local_path = images_out_dir / f'{stem}_{i}{suf}'
                i += 1

            # Guardar imagen
            with open(local_path, 'wb') as f:
                for chunk in resp.iter_content(8192):
                    f.write(chunk)

            print(f'    [OK] Imagen descargada: {safe_name}')

            # Ruta relativa desde el .md hasta la imagen
            rel = _relative_posix(md_file_path.parent, local_path)
            downloaded[url] = rel

            md_content = md_content[:m.start()] + f'![{alt_text}]({rel})' + md_content[m.end():]

        except Exception as e:
            print(f'    [WARN] Fallo al descargar imagen: {url} — {e}', file=sys.stderr)

    return md_content


def _relative_posix(from_dir: Path, to_file: Path) -> str:
    """Devuelve la ruta relativa en formato POSIX (barras /) con espacios %20."""
    try:
        rel = os.path.relpath(str(to_file), str(from_dir))
        return rel.replace('\\', '/').replace(' ', '%20')
    except ValueError:
        # En Windows puede fallar cross-drive; usar ruta absoluta como fallback
        return to_file.as_posix()


# ---------------------------------------------------------------------------
# Corrección de enlaces internos
# ---------------------------------------------------------------------------

def fix_internal_links(
    md_content: str,
    current_file_path: Path,
    article_paths: dict[str, str],
    article_paths_by_title: dict[str, str],
    folder_paths: Optional[dict[str, str]],
    counter: list[int],
) -> str:
    """Repara enlaces internos de Freshdesk apuntando a ficheros .md locales."""
    if folder_paths is None:
        folder_paths = {}

    def get_relative_local_path(target_abs: str) -> str:
        return _relative_posix(current_file_path.parent, Path(target_abs))

    def resolve_target_path(article_id: str, link_text: str, url: str) -> Optional[str]:
        if article_id and article_id in article_paths:
            return article_paths[article_id]

        candidates: list[str] = []
        if link_text:
            candidates.append(normalize_article_key(link_text))
        if url:
            slug_m = re.search(r'/articles/\d+-([^/?#)]+)', url, re.IGNORECASE)
            if slug_m:
                candidates.append(normalize_article_key(slug_m.group(1)))

        for ck in dict.fromkeys(c for c in candidates if c):
            if ck in article_paths_by_title:
                return article_paths_by_title[ck]
            tokens = [t for t in ck.split(' ') if len(t) >= 3]
            if tokens:
                hits = [k for k in article_paths_by_title if all(t in k for t in tokens)]
                hits.sort(key=len)
                if len(hits) == 1:
                    return article_paths_by_title[hits[0]]
        return None

    # 1. Reemplazar enlaces Markdown con /articles/ID
    md_rx = re.compile(r'(?is)\[([^\]]*)\]\(([^)]*?/articles/(\d+)[^)]*?)\)')
    matches = list(md_rx.finditer(md_content))
    for m in reversed(matches):
        alt    = m.group(1)
        url    = m.group(2)
        art_id = m.group(3).strip()
        target = resolve_target_path(art_id, alt, url)
        if target:
            try:
                rel = get_relative_local_path(target)
                new_link = f'[{alt}]({rel})'
                md_content = md_content[:m.start()] + new_link + md_content[m.end():]
                counter[0] += 1
            except Exception:
                pass

    # 2. URLs crudas que no están ya en Markdown
    raw_rx = re.compile(r'(?i)(?<!\]\()(\bhttps?://[^\s()]*?/articles/(\d+)[^\s()]*)\b')
    raw_matches = list(raw_rx.finditer(md_content))
    for m in reversed(raw_matches):
        url    = m.group(1)
        art_id = m.group(2).strip()
        target = resolve_target_path(art_id, '', url)
        if target:
            try:
                rel = get_relative_local_path(target)
                new_link = f'[Enlace Interno]({rel})'
                md_content = md_content[:m.start()] + new_link + md_content[m.end():]
                counter[0] += 1
            except Exception:
                pass

    # Limpiar artefactos del tipo [](freshdesk)[Titulo](local.md)
    md_content = re.sub(
        r'\[\]\((https?://[^)]*?/articles/[^)]*)\)\s*\[([^\]]+)\]\(([^)]+?\.md)\)',
        r'[\2](\3)', md_content, flags=re.IGNORECASE
    )
    md_content = re.sub(
        r'\[\]\(([^)]+?\.md)\)\s*\[([^\]]+)\]\(([^)]+?\.md)\)',
        r'[\2](\3)', md_content, flags=re.IGNORECASE
    )

    # Reemplazar [](freshdesk) + texto siguiente
    empty_rx = re.compile(r'\[\]\(([^)]*?/articles/(\d+)[^)]*?)\)((?:[^\s\[\]\(\),.;:!?][^,\n\r\)\]]{0,120}))')
    empty_matches = list(empty_rx.finditer(md_content))
    for m in reversed(empty_matches):
        url       = m.group(1)
        art_id    = m.group(2).strip()
        candidate = re.sub(r'\s+', ' ', m.group(3)).strip()
        if not candidate:
            continue
        word_count = len([w for w in candidate.split(' ') if w])
        if word_count > 8:
            continue
        target = resolve_target_path(art_id, candidate, url)
        if target:
            try:
                rel = get_relative_local_path(target)
                replacement = f'[{candidate}]({rel})'
                md_content = md_content[:m.start()] + replacement + md_content[m.end():]
                counter[0] += 1
            except Exception:
                pass

    # Eliminar enlaces vacíos a Freshdesk sin texto
    md_content = re.sub(
        r'\[\]\((https?://[^)]*?(?:freshdesk\.com|freshdesk\.es)[^)]*?/articles/[^)]*)\)',
        '', md_content, flags=re.IGNORECASE
    )

    # Reemplazar enlaces Markdown a carpetas Freshdesk por rutas locales si se conocen.
    folder_rx = re.compile(r'(?is)\[([^\]]*)\]\(([^)]*?/support/solutions/folders/(\d+)[^)]*?)\)')
    for m in reversed(list(folder_rx.finditer(md_content))):
        alt = m.group(1)
        fid = m.group(3).strip()
        if fid in folder_paths:
            try:
                rel = get_relative_local_path(folder_paths[fid])
                if not rel.endswith('/'):
                    rel += '/'
                md_content = md_content[:m.start()] + f'[{alt}]({rel})' + md_content[m.end():]
                counter[0] += 1
            except Exception:
                pass

    raw_folder_rx = re.compile(r'(?i)(?<!\]\()(\bhttps?://[^\s()]*?/support/solutions/folders/(\d+)[^\s()]*)\b')
    for m in reversed(list(raw_folder_rx.finditer(md_content))):
        fid = m.group(2).strip()
        if fid in folder_paths:
            try:
                rel = get_relative_local_path(folder_paths[fid])
                if not rel.endswith('/'):
                    rel += '/'
                md_content = md_content[:m.start()] + f'[Ver Carpeta]({rel})' + md_content[m.end():]
                counter[0] += 1
            except Exception:
                pass

    # Degradar a texto plano los enlaces de Freshdesk no resueltos
    md_content = re.sub(
        r'\[([^\]]+)\]\((https?://[^)]*?(?:freshdesk\.com|freshdesk\.es)[^)]*?/articles/[^)]*)\)',
        r'\1', md_content, flags=re.IGNORECASE
    )
    md_content = re.sub(
        r'https?://[^\s]*?(?:freshdesk\.com|freshdesk\.es)[^\s]*?/articles/[^\s)]+',
        '', md_content, flags=re.IGNORECASE
    )

    # Reemplazar URLs de carpetas Freshdesk por el nuevo dominio ayuda.ahora.es
    md_content = re.sub(
        r'https?://[^\s)]*?(?:freshdesk\.com|freshdesk\.es)[^\s)]*?/(?:support/solutions|a/forums)/folders/(\d+)[^\s)]*',
        r'https://ayuda.ahora.es/{{producto}}/\1',
        md_content, flags=re.IGNORECASE
    )

    return md_content


# ---------------------------------------------------------------------------
# Postproceso ERP de enlaces
# ---------------------------------------------------------------------------

def _erp_link_words(text: str) -> set[str]:
    text = urllib.parse.unquote(text or '')
    if text.lower().endswith('.md'):
        text = text[:-3]
    text = re.sub(
        r'^(erp|ventas|compras|logistica|contabilidad|configuracion|facturacion|gestion|sga|reporting)\b',
        '',
        text,
        flags=re.IGNORECASE,
    )
    return set(re.findall(r'[a-zA-Z0-9áéíóúÁÉÍÓÚñÑ]{3,}', text.lower()))


def postprocess_erp_links(docs_root: Path) -> int:
    """
    Segunda pasada para enlaces relativos rotos en la documentación.
    Está aislada para poder quitarla fácilmente si hiciera falta.
    """
    root_path = docs_root.resolve()
    if not root_path.exists():
        return 0

    all_files = list(root_path.rglob('*.md'))
    file_word_map: list[dict[str, object]] = []
    for f in all_files:
        words = _erp_link_words(f.stem)
        if words:
            file_word_map.append({'path': f, 'words': words, 'name': f.stem})

    link_pattern = re.compile(r'\[([^\]]*)\]\(([^)]+)\)')
    fixed_count = 0

    for filepath in root_path.rglob('*.md'):
        content = filepath.read_text(encoding='utf-8')
        new_content = content
        matches = list(link_pattern.finditer(content))

        for match in reversed(matches):
            original_text = match.group(1)
            original_url = match.group(2).strip()

            if original_url.startswith(('http://', 'https://', 'mailto:', 'ftp://', '//')):
                continue
            if 'docs_assets' in original_url:
                continue

            link_path_part = original_url.split('#', 1)[0].split('?', 1)[0]
            clean_link_path = urllib.parse.unquote(link_path_part)
            target_path = (filepath.parent / clean_link_path).resolve()

            if target_path.exists() and target_path.is_file() and clean_link_path.lower().endswith('.md'):
                continue

            filename_to_find = Path(clean_link_path).name
            search_words = _erp_link_words(filename_to_find) | _erp_link_words(original_text)
            if not search_words:
                continue

            best_score = 0.0
            best_candidate: Optional[Path] = None
            lower_find = filename_to_find.lower()

            for item in file_word_map:
                common = search_words.intersection(item['words'])  # type: ignore[index]
                score = float(len(common))
                lower_name = str(item['name']).lower()
                if lower_find and (lower_find in lower_name or lower_name in lower_find):
                    score += 3.0
                if 'ERP' in str(item['path']):
                    score += 0.2
                if score > best_score:
                    best_score = score
                    best_candidate = item['path']  # type: ignore[assignment]

            if best_candidate and best_score >= 1.0:
                rel_path = os.path.relpath(best_candidate, filepath.parent).replace('\\', '/')
                new_link_url = rel_path
                link_parts = original_url.split('#', 1)
                if len(link_parts) > 1:
                    new_link_url += '#' + link_parts[1]
                if new_link_url == original_url:
                    continue
                start, end = match.span(2)
                new_content = new_content[:start] + new_link_url + new_content[end:]
                fixed_count += 1

        if new_content != content:
            filepath.write_text(new_content, encoding='utf-8')

    return fixed_count


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Genera estructura MkDocs docs/CATEGORIA/CARPETA/ARTICULO.md desde SQL Server.'
    )
    parser.add_argument(
        '--connection-string',
        help='ODBC Connection string de SQL Server'
    )
    parser.add_argument('--env-file', default='.env', help='Archivo .env con la connection string')
    parser.add_argument('--output-dir', default='.', help='Directorio base donde se generará la carpeta docs')
    parser.add_argument('--categories', nargs='*', default=[], help='Filtros de categoría')
    parser.add_argument('--category-contains', action='store_true', help='Usar "contiene" en lugar de exacto')
    parser.add_argument('--product', default='', help='Filtro por producto de la categoría')
    parser.add_argument('--product-contains', action='store_true', help='Usar "contiene" en lugar de exacto para el producto')
    parser.add_argument('--clean-output', action='store_true', help='Borrar output antes de generar')
    args = parser.parse_args()

    print('=====================================================')
    print(' Generando estructura MkDocs (Categoría > Carpeta) ')
    print('=====================================================')

    env_file = Path(args.env_file)
    connection_string = resolve_connection_string(args.connection_string, env_file)
    output_dir  = Path(args.output_dir)
    docs_folder = output_dir / 'docs'
    images_folder = docs_folder / 'docs_assets' / 'images'
    state_path = get_state_path(output_dir)
    generation_state = load_generation_state(output_dir)
    incremental_mode = state_path.exists()
    reset_run_state(output_dir)

    if incremental_mode:
        last_generated_at = generation_state.get('meta', {}).get('last_generated_at', '')
        print(f'[*] Modo incremental activo desde {last_generated_at or "(sin fecha válida)"}')
    else:
        print('[*] No existe generation_state.json; se generarán todos los artículos que encajen con el filtro del usuario.')

    if args.clean_output and docs_folder.exists():
        import shutil
        shutil.rmtree(docs_folder)
    docs_folder.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    conn = pyodbc.connect(connection_string)
    cursor = conn.cursor()

    enlaces_reparados = [0]  # lista para mutabilidad en funciones anidadas
    wiki_broken_images: list[tuple[str, str]] = []

    # ==========================================
    # 1. CARGAR CATEGORÍAS
    # ==========================================
    print('[*] Leyendo Categorías...')
    dic_categorias: dict[str, str] = {}
    dic_categorias_raw: dict[str, str] = {}
    dic_categorias_product: dict[str, str] = {}

    cursor.execute("SELECT JSONDATA, Product FROM [dbo].[freshdesk_categories] WHERE JSONDATA IS NOT NULL")
    for row in cursor.fetchall():
        try:
            j = json.loads(row[0])
            product_val = row[1] if len(row) > 1 and row[1] else ''
            cid  = str(j.get('Id') or j.get('id') or '')
            name = j.get('Name') or j.get('name') or ''
            producto = str(product_val).strip()
            if cid:
                dic_categorias[cid] = get_safe_filename(name, f'Categoria_{cid}')
                dic_categorias_raw[cid] = str(name)
                dic_categorias_product[cid] = producto
        except Exception:
            pass

    # Filtrar categorías
    selected_ids: list[str] = []
    selected_names: list[str] = []
    product_filter = args.product
    
    if not product_filter and not args.categories:
        prompt = input('Introduce el producto al que pertenecen las categorías (vacío = todas): ').strip()
        if prompt:
            product_filter = prompt

    if product_filter:
        for cid, prod in dic_categorias_product.items():
            if args.product_contains:
                match = product_filter.lower() in prod.lower()
            else:
                match = prod.lower() == product_filter.lower()
            if match and cid not in selected_ids:
                selected_ids.append(cid)

        if not selected_ids:
            conn.close()
            sys.exit(f'No se encontraron categorías para el producto: {product_filter}')

        selected_names = [dic_categorias_raw[cid] for cid in selected_ids]
        print(f'[*] Categorías seleccionadas para el producto "{product_filter}": {", ".join(selected_names)}')
    elif args.categories:
        for f in args.categories:
            for cid, name in dic_categorias_raw.items():
                if args.category_contains:
                    match = f.lower() in name.lower()
                else:
                    match = name.lower() == f.lower()
                if match and cid not in selected_ids:
                    selected_ids.append(cid)

        if not selected_ids:
            conn.close()
            sys.exit(f'No se encontró ninguna categoría que coincida con: {", ".join(args.categories)}')

        selected_names = [dic_categorias_raw[cid] for cid in selected_ids]
        print(f'[*] Categorías seleccionadas: {", ".join(selected_names)}')
    else:
        selected_names = list(dic_categorias_raw.values())

    # ==========================================
    # 2. CARGAR CARPETAS
    # ==========================================
    print('[*] Leyendo Carpetas...')
    dic_carpetas: dict[str, str] = {}
    dic_carpetas_rutas: dict[str, str] = {}
    cursor.execute("SELECT JSONDATA FROM [dbo].[freshdesk_folders] WHERE JSONDATA IS NOT NULL")
    for row in cursor.fetchall():
        try:
            j = json.loads(row[0])
            fid  = str(j.get('Id') or j.get('id') or '')
            name = j.get('Name') or j.get('name') or ''
            cat_id = str(j.get('CategoryId') or j.get('category_id') or '')
            if fid:
                safe_name = get_safe_filename(name, f'Carpeta_{fid}')
                dic_carpetas[fid] = safe_name
                if cat_id and cat_id in dic_categorias:
                    cat_name = dic_categorias[cat_id]
                    dic_carpetas_rutas[fid] = str((docs_folder / cat_name / safe_name).resolve())
        except Exception:
            pass

    cursor.execute("SELECT JSONDATA FROM [dbo].[freshdesk_articles] WHERE JSONDATA IS NOT NULL")
    all_article_rows = cursor.fetchall()
    planned_article_paths = build_article_output_plan(
        all_article_rows,
        docs_folder,
        dic_categorias,
        dic_carpetas,
        selected_ids=selected_ids,
    )

    # ==========================================
    # 3. PRE-CALCULAR RUTAS DE ARTÍCULOS
    # ==========================================
    print('[*] Pre-calculando rutas para enlaces internos...')
    dic_articulos_rutas: dict[str, str] = {}
    dic_articulos_rutas_por_titulo: dict[str, str] = {}

    for row in all_article_rows:
        try:
            raw = row[0]
            if not raw or not raw.strip():
                continue
            j = json.loads(raw)
            art_id = j.get('Id') or j.get('id')
            if art_id is None:
                continue
            cat_id    = str(j.get('CategoryId') or j.get('category_id') or '')
            if selected_ids and cat_id not in selected_ids:
                continue
            folder_id = str(j.get('FolderId')   or j.get('folder_id')   or '')
            title     = j.get('Title') or j.get('title') or ''

            planned_path = planned_article_paths.get(str(art_id))
            if planned_path is None:
                cat_name    = dic_categorias.get(cat_id, f'Categoria_Desconocida')
                folder_name = dic_carpetas.get(folder_id, f'Carpeta_Desconocida')
                clean_title = get_safe_filename(title, f'Articulo_{art_id}')
                planned_path = docs_folder / cat_name / folder_name / f'{clean_title}.md'

            path_abs = str(planned_path.resolve())
            str_id   = str(art_id).strip()
            dic_articulos_rutas[str_id] = path_abs

            title_key = normalize_article_key(title)
            if title_key and title_key not in dic_articulos_rutas_por_titulo:
                dic_articulos_rutas_por_titulo[title_key] = path_abs
        except Exception:
            pass

    # ==========================================
    # 4. PROCESAR ARTÍCULOS
    # ==========================================
    print('[*] Generando archivos .md...')
    count_ok = 0
    count_err = 0
    selected_article_count = 0
    pipeline_ok = True

    for row in all_article_rows:
        try:
            raw = row[0]
            if not raw or not raw.strip():
                continue
            articulo = json.loads(raw)
            cat_id = str(articulo.get('CategoryId') or articulo.get('category_id') or '')
            if selected_ids and cat_id not in selected_ids:
                continue
            folder_id = str(articulo.get('FolderId') or articulo.get('folder_id') or '')
            title = articulo.get('Title') or articulo.get('title') or ''
            updated_at = str(articulo.get('updated_at') or articulo.get('UpdatedAt') or '')
            md_path = planned_article_paths.get(str(articulo.get('Id') or articulo.get('id')))
            if md_path is None:
                clean_title = get_safe_filename(title, f'Articulo_{articulo.get("Id") or articulo.get("id")}')
                md_path = docs_folder / dic_categorias.get(cat_id, 'Categoria_Desconocida') / dic_carpetas.get(folder_id, 'Carpeta_Desconocida') / f'{clean_title}.md'
            if incremental_mode and not should_generate_article(
                generation_state,
                str(articulo.get('Id') or articulo.get('id')),
                updated_at,
                md_path,
            ):
                continue
            selected_article_count += 1
        except Exception:
            continue

    for index, row in enumerate(all_article_rows, start=1):
        try:
            raw = row[0]
            if not raw or not raw.strip():
                continue
            articulo = json.loads(raw)

            art_id = articulo.get('Id') or articulo.get('id')
            if art_id is None:
                continue

            folder_id = str(articulo.get('FolderId') or articulo.get('folder_id') or '')
            cat_id    = str(articulo.get('CategoryId') or articulo.get('category_id') or '')

            if selected_ids and cat_id not in selected_ids:
                continue

            cat_name    = dic_categorias.get(cat_id, 'Categoria_Desconocida')
            folder_name = dic_carpetas.get(folder_id, 'Carpeta_Desconocida')

            out_dir_art = docs_folder / cat_name / folder_name
            out_dir_art.mkdir(parents=True, exist_ok=True)

            title = articulo.get('Title') or articulo.get('title') or ''
            desc  = articulo.get('Description') or articulo.get('description') or ''
            updated_at = str(articulo.get('updated_at') or articulo.get('UpdatedAt') or '')

            md_path = planned_article_paths.get(str(art_id))
            if md_path is None:
                clean_title = get_safe_filename(title, f'Articulo_{art_id}')
                md_path = out_dir_art / f'{clean_title}.md'

            if incremental_mode and not should_generate_article(
                generation_state,
                str(art_id),
                updated_at,
                md_path,
            ):
                continue

            if count_ok == 0 or (count_ok + 1) % 25 == 0:
                current_pos = min(count_ok + 1, selected_article_count) if selected_article_count else count_ok + 1
                print(f'    -> [{current_pos}/{selected_article_count or "?"}] {title}', flush=True)

            md_content = convert_article_html_to_markdown(
                str(desc),
                docs_folder,
                md_path,
                images_folder,
                title,
                str(art_id),
                wiki_broken_images,
            )
            md_content = fix_internal_links(
                md_content, md_path,
                dic_articulos_rutas, dic_articulos_rutas_por_titulo,
                dic_carpetas_rutas,
                enlaces_reparados
            )

            md_path.write_text(f'# {title}\n\n{md_content}', encoding='utf-8')
            record_generated_article(
                output_dir,
                str(art_id),
                title=title,
                product=dic_categorias_product.get(cat_id, ''),
                category_id=cat_id,
                category_name=cat_name,
                folder_id=folder_id,
                folder_name=folder_name,
                path=md_path.relative_to(output_dir).as_posix(),
                source_updated_at=updated_at,
            )

            count_ok += 1
            if count_ok % 100 == 0:
                print(f'    -> {count_ok} generados...', flush=True)

        except Exception as e:
            count_err += 1
            continue

    cursor.close()
    conn.close()

    print('\n=====================================================')
    print(f' Finalizado: {count_ok} artículos .md en sus carpetas. ')
    print(f' Enlaces internos reparados a formato local: {enlaces_reparados[0]}')
    print('=====================================================')

    if wiki_broken_images:
        log_path = output_dir / 'wiki_ahora_images_log.txt'
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write("Imágenes de wiki.ahora.es no descargadas y sus artículos:\n" + "="*60 + "\n\n")
            for url, art in wiki_broken_images:
                f.write(f"Artículo: {art}\nURL: {url}\n\n")
        print(f'[*] Log de imágenes de wiki.ahora.es generado en {log_path}')

    try:
        print('[*] Ejecutando postproceso interno de enlaces ERP...')
        erp_fixed = postprocess_erp_links(docs_folder)
        print(f'[*] Enlaces ERP corregidos en segunda pasada: {erp_fixed}')
    except Exception as e:
        pipeline_ok = False
        print(f'[WARN] No se pudo completar el postproceso ERP de enlaces: {e}')

    try:
        import subprocess
        script_path = Path(__file__).parent / 'repair_links_pipeline.py'
        if script_path.exists():
            print('[*] Ejecutando pipeline de reparación de enlaces...')
            subprocess.run(
                [sys.executable, str(script_path), '--docs-dir', str(docs_folder)],
                check=True,
            )
        else:
            print('[WARN] No se encontró repair_links_pipeline.py; se omite esa fase.')
    except Exception as e:
        pipeline_ok = False
        print(f'[WARN] No se pudo ejecutar el pipeline de reparación de enlaces: {e}')

    try:
        author_rc = run_author_articles(
            category_names=selected_names,
            output_dir=output_dir,
            env_file=env_file,
            connection_string=connection_string,
        )
        if author_rc != 0:
            pipeline_ok = False
            print(f'[WARN] author_articles.py terminó con código {author_rc}')
    except Exception as e:
        pipeline_ok = False
        print(f'[WARN] No se pudo ejecutar author_articles.py al finalizar migrate.py: {e}')

    try:
        if pipeline_ok:
            executed_at = finalize_generation_state(output_dir)
            print(f'[*] generation_state.json actualizado a {executed_at}')
        else:
            print('[WARN] No se actualiza generation_state.json porque el flujo no ha terminado completamente bien.')
    except Exception as e:
        print(f'[WARN] No se pudo actualizar generation_state.json: {e}')


if __name__ == '__main__':
    main()
