"""
author_articles.py
==================
Parche experimental sobre migrate.py para artículos filtrados por autor.
Genera solo artículos del autor objetivo e intenta sanear HTML problemático
antes de convertirlo a Markdown.

Dependencias:
    pip install pyodbc requests markdownify
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

from markdownify import markdownify as md
from pygments.lexers import guess_lexer
from pygments.util import ClassNotFound
import pyodbc
import requests
from generation_state import (
    get_state_path,
    load_generation_state,
    record_generated_article,
    should_generate_article,
)

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
    decoded = html_lib.unescape(text)
    decoded = urllib.parse.unquote(decoded)
    # Eliminar marcas diacríticas (acentos)
    normalized = unicodedata.normalize('NFD', decoded)
    result = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
    result = result.lower()
    result = re.sub(r'[^a-z0-9]+', ' ', result)
    result = re.sub(r'\s+', ' ', result).strip()
    return result


def build_article_lookup_keys(title: str) -> list[str]:
    """Genera variantes normalizadas de un título para mejorar la resolución de enlaces."""
    if not title or not title.strip():
        return []

    variants: list[str] = []

    def add(value: str) -> None:
        key = normalize_article_key(value)
        if key and key not in variants:
            variants.append(key)

    add(title)
    add(get_safe_filename(title, title))

    separators = [' - ', ' – ', ' — ', ': ', ' | ', ' / ']
    for separator in separators:
        if separator in title:
            parts = [part.strip() for part in title.split(separator) if part.strip()]
            for part in parts:
                add(part)
            if len(parts) >= 2:
                add(parts[-1])
                add(' '.join(parts[-2:]))

    # También registrar el título sin contenido entre paréntesis/corchetes.
    simplified = re.sub(r'[\(\[\{].*?[\)\]\}]', ' ', title)
    add(simplified)

    return variants


def build_article_output_plan(
    articles: list[dict],
    docs_folder: Path,
    dic_categorias: dict[str, str],
    dic_carpetas: dict[str, str],
) -> dict[str, Path]:
    """Calcula rutas de salida evitando colisiones de nombre dentro de la misma carpeta."""
    grouped: dict[str, list[tuple[str, str, str, str, str]]] = defaultdict(list)

    for articulo in articles:
        try:
            art_id = articulo.get('Id') or articulo.get('id')
            if art_id is None:
                continue

            cat_id = str(articulo.get('CategoryId') or articulo.get('category_id') or '')
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


def is_target_author_article(description: str) -> bool:
    """Detecta artículos atribuidos al autor objetivo a partir del description HTML."""
    if not description:
        return False
    desc_norm = html_lib.unescape(description).lower()
    return 'autor: daniel' in desc_norm


def sanitize_target_author_html(html: str) -> str:
    """Aplica una limpieza agresiva a los patrones HTML problemáticos del autor objetivo."""
    if not html or not html.strip():
        return ""

    html = html.replace('\xa0', ' ')
    html = html.replace('&amp;amp;', '&amp;')
    html = html.replace('&amp;nbsp;', '&nbsp;')

    # Quitar spans vacíos y párrafos/divs completamente vacíos que meten ruido.
    for _ in range(2):
        html = re.sub(r'(?is)<span[^>]*>\s*</span>', '', html)
        html = re.sub(r'(?is)<p[^>]*>\s*(?:&nbsp;|\s|<br\s*/?>)*</p>', '', html)
        html = re.sub(r'(?is)<div[^>]*>\s*(?:&nbsp;|\s|<br\s*/?>)*</div>', '', html)

    # Normalizar anchors vacíos típicos de Freshdesk/video embeds.
    html = re.sub(
        r'(?is)<a([^>]+href=["\']?[^"\'>]+["\']?[^>]*)>\s*(?:&nbsp;|\s|<span[^>]*>\s*</span>|<br\s*/?>)*</a>',
        r'<a\1>&nbsp;</a>',
        html,
    )

    # Reducir ráfagas de <br> absurdas fuera de bloques protegidos.
    html = re.sub(r'(?is)(?:<br\s*/?>\s*){3,}', '<br><br>', html)

    def _looks_like_code_line(text: str) -> bool:
        text = re.sub(r'(?is)<br\s*/?>', '\n', text or '')
        text = html_lib.unescape(re.sub(r'<[^>]+>', ' ', text))
        text = text.replace('\xa0', ' ')
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n+', '\n', text).strip()
        if not text:
            return False
        code_markers = [
            r"^'?Sub\s+\w+",
            r"^End\s+Sub$",
            r"^'?Function\s+\w+",
            r"^End\s+Function$",
            r"^Public\s+Class\b",
            r"^End\s+Class$",
            r"^Public\s+Sub\b",
            r"^Private\s+\w+",
            r"^Public\s+Property\b",
            r"^End\s+Property$",
            r"^Get$",
            r"^End\s+Get$",
            r"^Set\s*\(",
            r"^End\s+Set$",
            r"^Return\b",
            r"^MsgBox\s*\(",
            r"^Dim\s+\w+",
            r"^Set\s+\w+\s*=",
            r"^If\b",
            r"^Else\b",
            r"^ElseIf\b",
            r"^For\b",
            r"^Next\b",
            r"^With\b",
            r"^End\s+With$",
            r"^\w+\.\w+",
            r"^\.\w+",
            r"^'[^']*",
        ]
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        if not lines:
            return False

        def line_looks_code(line: str) -> bool:
            return any(re.search(pattern, line, re.IGNORECASE) for pattern in code_markers)

        if len(lines) == 1:
            return line_looks_code(lines[0])

        code_hits = sum(1 for line in lines if line_looks_code(line))
        first_line_is_code = line_looks_code(lines[0])
        return first_line_is_code or code_hits >= max(2, (len(lines) + 1) // 2)

    def _split_mixed_paragraph(m: re.Match) -> str:
        content = m.group(1)
        if re.search(r'(?is)<(?:code|pre)\b', content):
            return m.group(0)
        parts = re.split(r'(?is)<br\s*/?>\s*<br\s*/?>', content)
        if len(parts) < 2:
            return m.group(0)
        prose = '<br><br>'.join(parts[:-1]).strip()
        tail = parts[-1].strip()
        if not _looks_like_code_line(tail):
            return m.group(0)
        result = ''
        if prose:
            result += f'<p>{prose}</p>'
        result += f'<p>{tail}</p>'
        return result

    html = re.sub(r'(?is)<p[^>]*>(.*?)</p>', _split_mixed_paragraph, html)

    # El autor objetivo suele trocear código como <p><code>...</code></p> en múltiples párrafos.
    def _merge_paragraph_code_blocks(m: re.Match) -> str:
        block = m.group(0)
        parts = re.findall(r'(?is)<p[^>]*>\s*<code[^>]*>(.*?)</code>\s*</p>', block)
        cleaned_parts: list[str] = []
        for part in parts:
            part = re.sub(r'(?is)<br\s*/?>', '\n', part)
            part = re.sub(r'(?is)</?p[^>]*>', '\n', part)
            part = re.sub(r'(?is)</?div[^>]*>', '\n', part)
            part = re.sub(r'(?is)<span[^>]*>', '', part)
            part = re.sub(r'(?is)</span>', '', part)
            cleaned_parts.append(part.strip('\n'))
        merged = '\n'.join(p for p in cleaned_parts if p.strip())
        return f'<pre>{merged}</pre>' if merged.strip() else ''

    html = re.sub(
        r'(?is)(?:<p[^>]*>\s*<code[^>]*>.*?</code>\s*</p>\s*){2,}',
        _merge_paragraph_code_blocks,
        html,
    )

    # Algunos artículos meten un único <p> con <code> anidado dentro del propio bloque.
    def _normalize_nested_code_paragraph(m: re.Match) -> str:
        paragraph = m.group(0)
        if paragraph.lower().count('<code') < 2:
            return paragraph
        inner = m.group(1)
        if '<code' not in inner.lower():
            return paragraph
        inner = re.sub(r'(?is)</?code[^>]*>', '', inner)
        if len(re.findall(r'(?is)<br\s*/?>', inner)) < 2:
            return f'<p><code>{inner}</code></p>'
        inner = re.sub(r'(?is)<br\s*/?>', '\n', inner)
        return f'<pre>{inner}</pre>'

    html = re.sub(
        r'(?is)<p[^>]*>(.*?)</p>',
        _normalize_nested_code_paragraph,
        html,
    )

    def _strip_nested_code_inside_pre(m: re.Match) -> str:
        attrs = m.group(1) or ''
        inner = m.group(2) or ''
        inner = re.sub(r'(?is)</?code[^>]*>', '', inner)
        return f'<pre{attrs}>{inner}</pre>'

    html = re.sub(
        r'(?is)<pre([^>]*)>(.*?)</pre>',
        _strip_nested_code_inside_pre,
        html,
    )

    # También convertir a <pre> cuando hay un único <code> de párrafo con muchos <br>.
    def _single_code_para_to_pre(m: re.Match) -> str:
        content = m.group(1)
        if len(re.findall(r'(?is)<br\s*/?>', content)) < 2:
            return m.group(0)
        content = re.sub(r'(?is)</?code[^>]*>', '', content)
        content = re.sub(r'(?is)<br\s*/?>', '\n', content)
        return f'<pre>{content}</pre>'

    html = re.sub(
        r'(?is)<p[^>]*>\s*<code[^>]*>(.*?)</code>\s*</p>',
        _single_code_para_to_pre,
        html,
    )

    def _merge_plain_code_paragraphs(m: re.Match) -> str:
        block = m.group(0)
        paragraphs = re.findall(r'(?is)<p[^>]*>(.*?)</p>', block)
        cleaned_parts: list[str] = []
        for part in paragraphs:
            part = re.sub(r'(?is)<br\s*/?>', '\n', part)
            part = html_lib.unescape(part)
            part = part.replace('\xa0', ' ')
            part = re.sub(r'(?is)<[^>]+>', '', part)
            part = re.sub(r'[ \t]+\n', '\n', part)
            part = re.sub(r'\n[ \t]+', '\n', part)
            cleaned_parts.append(part.strip('\n'))
        merged = '\n'.join(p for p in cleaned_parts if p.strip())
        return f'<pre>{merged}</pre>' if merged.strip() else block

    paragraph_rx = re.compile(r'(?is)<p[^>]*>.*?</p>')
    pieces: list[str] = []
    last_end = 0
    run_parts: list[re.Match] = []

    def flush_run() -> None:
        nonlocal run_parts
        if not run_parts:
            return
        run_html = ''.join(m.group(0) for m in run_parts)
        if len(run_parts) >= 2:
            pieces.append(_merge_plain_code_paragraphs(re.match(r'(?is).*', run_html)))
        else:
            pieces.append(run_html)
        run_parts = []

    for m in paragraph_rx.finditer(html):
        pieces.append(html[last_end:m.start()])
        paragraph_inner = m.group(0)
        if _looks_like_code_line(paragraph_inner):
            run_parts.append(m)
        else:
            flush_run()
            pieces.append(m.group(0))
        last_end = m.end()

    flush_run()
    pieces.append(html[last_end:])
    html = ''.join(pieces)

    return html


# ---------------------------------------------------------------------------
# Motor de conversión HTML → Markdown
# ---------------------------------------------------------------------------

# Compilar las regex de SQL una sola vez (rendimiento)
_SQL_START = re.compile(
    r'^\s*(IF\s+NOT\s+EXISTS|SELECT\s+|UPDATE\s+[\[\w]|INSERT\s+INTO|DELETE\s+FROM'
     r'|DECLARE\s+@|BEGIN\b|CREATE\s+(?:TABLE|PROC|VIEW|FUNCTION)|ALTER\s+(?:TABLE|PROC|VIEW|FUNCTION)'
     r'|USE\s+\[|EXEC\s+\w|SET\s+(?:ANSI|NOCOUNT|@))',
    re.IGNORECASE
)
_SQL_CONTINUE = re.compile(
    r'^\s*(--|@@|@\w+|AND\b|OR\b|WHERE\b|FROM\b|JOIN\b|ON\b|LEFT\b|RIGHT\b|INNER\b'
     r'|GROUP\b|ORDER\b|HAVING\b|VALUES\b|SET\b|END\b|IF\b|ELSE\b|CASE\b|WHEN\b|THEN\b'
     r'|AS\b|GO\b|INSERT\s+INTO\b|UPDATE\b|DELETE\s+FROM\b|SELECT\b'
     r'|\s*\[\w+\]\s*|PRINT\b|EXEC\b|DECLARE\b|\(|\)|\w+\s*=|\'\')',
    re.IGNORECASE
)

FLAG = re.IGNORECASE | re.DOTALL


def _normalize_detected_lang(lang: str) -> str:
    """Normaliza aliases de detectores externos a nombres útiles para fences Markdown."""
    normalized = (lang or '').strip().lower()
    lang_map = {
        'c#': 'csharp',
        'csharp': 'csharp',
        'cs': 'csharp',
        'vb.net': 'vb',
        'vbnet': 'vb',
        'vb': 'vb',
        'visualbasic': 'vb',
        't-sql': 'sql',
        'tsql': 'sql',
        'transact-sql': 'sql',
        'sql': 'sql',
        'js': 'javascript',
        'javascript': 'javascript',
        'json': 'json',
        'html': 'html',
        'xml': 'xml',
        'powershell': 'powershell',
        'pwsh': 'powershell',
        'ps1': 'powershell',
        'bash': 'bash',
        'sh': 'bash',
        'shell': 'bash',
    }
    return lang_map.get(normalized, '')


def _detect_lang_with_pygments(code: str) -> str:
    """Usa Pygments como fallback para inferir el lenguaje del bloque."""
    if not code or len(code.strip()) < 12:
        return ''
    try:
        lexer = guess_lexer(code)
    except ClassNotFound:
        return ''
    except Exception:
        return ''

    aliases = getattr(lexer, 'aliases', None) or []
    for alias in aliases:
        lang = _normalize_detected_lang(alias)
        if lang:
            return lang

    lexer_name = _normalize_detected_lang(getattr(lexer, 'name', ''))
    return lexer_name


def _normalize_markdown_fences(md_text: str) -> str:
    """Normaliza fences Markdown para que siempre queden en líneas limpias y separadas."""
    if not md_text:
        return md_text

    # Asegurar salto de línea antes de una apertura de fence si quedó pegada a texto.
    md_text = re.sub(r'([^\n])(```[A-Za-z0-9_-]*)', r'\1\n\2', md_text)
    # Asegurar salto de línea después de la línea de apertura.
    md_text = re.sub(r'(```[A-Za-z0-9_-]*)[ \t]*\n?', r'\1\n', md_text)
    # Asegurar que el cierre esté en su propia línea.
    md_text = re.sub(r'([^\n])\n?```', r'\1\n```', md_text)
    # Evitar espacios o texto residual en líneas de fence.
    md_text = re.sub(r'(?m)^[ \t]*(```[A-Za-z0-9_-]*)[ \t]*$', r'\1', md_text)
    md_text = re.sub(r'(?m)^[ \t]*```[ \t]*$', '```', md_text)
    # Colapsar exceso de saltos alrededor de fences.
    md_text = re.sub(r'\n{3,}```', '\n\n```', md_text)
    md_text = re.sub(r'```\n{3,}', '```\n\n', md_text)
    return md_text


def _looks_like_markdown_code_line(line: str) -> bool:
    stripped = (line or '').strip()
    if not stripped:
        return False
    if stripped.startswith(('#', '-', '*', '>', '[](')):
        return False
    patterns = [
        r"^'?Sub\s+\w+",
        r"^End\s+Sub$",
        r"^'?Function\s+\w+",
        r"^End\s+Function$",
        r"^Public\s+Class\b",
        r"^End\s+Class$",
        r"^Public\s+Sub\b",
        r"^Private\s+\w+",
        r"^Public\s+Property\b",
        r"^End\s+Property$",
        r"^Get$",
        r"^End\s+Get$",
        r"^Set\s*\(",
        r"^End\s+Set$",
        r"^Return\b",
        r"^MsgBox\s*\(",
        r"^Dim\s+\w+",
        r"^Set\s+\w+\s*=",
        r"^If\b",
        r"^Else\b",
        r"^ElseIf\b",
        r"^For\b",
        r"^Next\b",
        r"^With\b",
        r"^End\s+With$",
        r"^\w+\.\w+",
        r"^\.\w+",
        r"^(SELECT|UPDATE|INSERT|DELETE|DECLARE|IF\s+NOT\s+EXISTS|CREATE\s+(?:TABLE|PROC|VIEW|FUNCTION)|ALTER\s+(?:TABLE|PROC|VIEW|FUNCTION)|EXEC)\b",
    ]
    return any(re.search(pattern, stripped, re.IGNORECASE) for pattern in patterns)


def _repair_markdown_code_blocks(md_text: str) -> str:
    """Ajusta fences mal partidos y envuelve rachas sueltas de código."""
    if not md_text:
        return md_text

    md_text = re.sub(
        r'(\*\*Ver código ejemplo\*\*|\*\*Ver c[oó]digo ejemplo\*\*)\n```\n\n```(\w+)\n',
        r'\1\n\n```\2\n',
        md_text,
        flags=re.IGNORECASE,
    )

    def _split_and_retag_fence(m: re.Match) -> str:
        lang = (m.group(1) or '').strip()
        content = m.group(2) or ''
        detected = _detect_code_lang(content)
        if detected:
            lang = detected

        split_markers = [
            '\n##### ',
            '\nPara llamarla desde el ERP se realizar',
            '\nEn este ejemplo se mostrar',
        ]
        split_index = -1
        for marker in split_markers:
            idx = content.find(marker)
            if idx != -1 and (split_index == -1 or idx < split_index):
                split_index = idx

        if split_index != -1:
            code_part = content[:split_index].rstrip()
            tail_part = content[split_index:].lstrip('\n')
            parts: list[str] = []
            if code_part:
                parts.append(f'```{lang}\n{code_part}\n```')
            if tail_part:
                parts.append(tail_part)
            return '\n\n'.join(parts)

        return f'```{lang}\n{content}\n```'

    md_text = re.sub(r'```(\w*)\n(.*?)```', _split_and_retag_fence, md_text, flags=re.DOTALL)

    lines = md_text.split('\n')
    new_lines: list[str] = []
    run: list[str] = []
    in_fence = False

    def flush_run() -> None:
        nonlocal run
        code_lines = [ln for ln in run if ln.strip()]
        if len(code_lines) >= 2:
            content = '\n'.join(run).strip('\n')
            lang = _detect_code_lang(content)
            new_lines.append(f'```{lang}')
            new_lines.extend(content.split('\n'))
            new_lines.append('```')
        else:
            new_lines.extend(run)
        run = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith('```'):
            flush_run()
            in_fence = not in_fence
            new_lines.append(line)
            continue
        if in_fence:
            new_lines.append(line)
            continue
        if _looks_like_markdown_code_line(line) or (run and not stripped):
            run.append(line)
        else:
            flush_run()
            new_lines.append(line)

    flush_run()
    return '\n'.join(new_lines)


def _detect_code_lang(code: str) -> str:
    """Detecta el lenguaje de un bloque de código para el hint de la valla."""
    stripped = code.strip()

    if re.search(r'(?im)^\s*(Sub\s+\w+\s*\(|End\s+Sub\b|Function\s+\w+\s*\(|End\s+Function\b|Dim\s+\w+|Set\s+\w+\s*=|With\b|End\s+With\b|MsgBox\b|Public\s+Class\b|End\s+Class\b|Public\s+Sub\b|Private\s+\w+|Public\s+Property\b|End\s+Property\b|Get\b|End\s+Get\b|Set\s*\(|End\s+Set\b|Return\b|\.\w+\s*=)', stripped):
        return 'vb'
    if re.search(r'\b(SELECT|UPDATE|INSERT|DELETE|DECLARE|IF\s+NOT\s+EXISTS|BEGIN\s+TRAN|CREATE\s+(?:TABLE|PROC|VIEW|FUNCTION)|ALTER\s+(?:TABLE|PROC|VIEW|FUNCTION)|EXEC\b|MERGE\b|WITH\s+\w+\s+AS)\b', stripped, re.IGNORECASE):
        return 'sql'
    if re.search(r'\b(function|var|let|const|=>|console\.log|document\.|window\.)\b', stripped, re.IGNORECASE):
        return 'javascript'
    if re.search(r'\b(using\s+System|public\s+class|private|protected|internal|void|string|int|namespace\s+\w+|public\s+static)\b', stripped, re.IGNORECASE):
        return 'csharp'
    if re.search(r'(?m)^\s*<(?:html|div|span|p|table|tr|td|img|a|script|style)\b', stripped, re.IGNORECASE):
        return 'html'
    if re.search(r'(?m)^\s*<\?xml\b|^\s*<[\w:-]+(?:\s|>)', stripped, re.IGNORECASE):
        return 'xml'
    if re.search(r'(?m)^\s*\{[\s\S]*\}\s*$|^\s*\[[\s\S]*\]\s*$', stripped) and re.search(r'"\s*:\s*', stripped):
        return 'json'
    if re.search(r'(?m)^\s*(Get-|Set-|New-Object|Write-Host|Write-Output|\$[A-Za-z_]\w*\s*=)', stripped):
        return 'powershell'
    if re.search(r'(?m)^\s*(#!/bin/(?:ba)?sh|echo\s+|export\s+\w+=|if\s+\[|fi$)', stripped):
        return 'bash'

    return _detect_lang_with_pygments(stripped)


def convert_html_to_markdown(html: str) -> str:
    """Convierte HTML a Markdown usando markdownify + post-procesado propio."""
    if not html or not html.strip():
        return ""

    html = sanitize_target_author_html(html)

    # 1. Normalizar HTML
    html = html.replace('&nbsp;', ' ')
    html = html_lib.unescape(html)

    # ========================================================
    # PASO 0: PROTEGER ANCLAS VACIAS
    # ========================================================
    empty_link_map: dict[str, str] = {}
    empty_link_counter = 1

    def next_empty_link_token() -> str:
        nonlocal empty_link_counter
        token = f'%%EMPTYLINK_{empty_link_counter}%%'
        empty_link_counter += 1
        return token

    def _extract_empty_anchor(m: re.Match) -> str:
        href = (m.group(1) or '').strip()
        full_tag = m.group(0) or ''
        inner = re.sub(r'<[^>]+>', '', m.group(2) or '')
        inner = html_lib.unescape(inner).strip()
        if inner:
            return m.group(0)
        title_match = re.search(r'(?is)\btitle=["\'](.*?)["\']', full_tag)
        title = html_lib.unescape(title_match.group(1)).strip() if title_match else ''
        token = next_empty_link_token()
        if title:
            safe_title = title.replace('"', r'\"')
            empty_link_map[token] = f'[]({href} "{safe_title}")'
        else:
            empty_link_map[token] = f'[]({href})'
        return f' {token} '

    html = re.sub(
        r'(?is)<a[^>]+href=["\']?([^"\'\s>]+)["\']?[^>]*>(.*?)</a>',
        _extract_empty_anchor,
        html,
    )

    # ========================================================
    # PASO A: EXTRACCION SEGURA DE CODIGO HTML (<pre>, <code>)
    # ========================================================
    code_map: dict[str, str] = {}
    code_counter = 1

    def next_code_token(prefix: str) -> str:
        nonlocal code_counter
        token = f'%%{prefix}_{code_counter}%%'
        code_counter += 1
        return token

    # Simplificar anidamientos comunes
    html = re.sub(r'(?is)<pre[^>]*>\s*<code[^>]*>', '<pre>', html)
    html = re.sub(r'(?is)</code>\s*</pre>', '</pre>', html)

    # Unir bloques pre/code fragmentados (incluso separados por <p> u otras etiquetas)
    join_regex = r'(?is)</(?:pre|code)>\s*(?:<br\s*/?>|</?p[^>]*>|</?div[^>]*>|</?span[^>]*>|&nbsp;)*\s*<(?:pre|code)[^>]*>'
    html = re.sub(join_regex, '\n', html)
    html = re.sub(join_regex, '\n', html)

    def _extract_code_block(m: re.Match) -> str:
        code = m.group(1)
        original_tag = m.group(0)[:5]

        code = re.sub(r'(?is)<br\s*/?>', '\n', code)
        code = re.sub(r'(?is)</?p[^>]*>', '\n', code)
        code = re.sub(r'(?is)</?div[^>]*>', '\n', code)
        code = re.sub(r'<[^>]+>', '', code)
        code = code.replace('\r\n', '\n').strip()

        if not code.strip():
            return ''

        is_pre = bool(re.match(r'(?is)<pre', original_tag))
        token = next_code_token('CBLK' if '\n' in code or is_pre else 'CILN')
        code_map[token] = code
        return f'\n\n{token}\n\n' if token.startswith('%%CBLK_') else f' {token} '

    html = re.sub(r'(?is)<(?:pre|code)[^>]*>(.*?)</(?:pre|code)>', _extract_code_block, html)

    # Aplanar saltos estructurales del resto del HTML
    html = html.replace('\r\n', ' ')
    html = re.sub(r'[\r\n]+', ' ', html)

    # markdownify convierte el HTML restante; los tokens de código quedan protegidos.
    md_text = md(
        html,
        autolinks=False,
        bullets='-',
        code_language='',
        default_title=False,
        escape_asterisks=False,
        escape_underscores=False,
        escape_misc=False,
        heading_style='ATX',
        newline_style='spaces',
        strip_document='strip',
        strip_pre='strip',
        wrap=False,
    )

    for token, replacement in empty_link_map.items():
        md_text = md_text.replace(token, replacement)

    # ── PASO B: HEURÍSTICA PARA SQL REZAGADO EN TEXTO PLANO ──────────────
    # Solo se aplica a líneas fuera de bloques de código ya creados por markdownify.
    lines = md_text.split('\n')
    new_lines: list[str] = []
    current_block: list[str] = []
    in_sql    = False
    in_fence  = False          # dentro de un bloque ``` ya existente

    for line in lines:
        trimmed = line.strip()

        # Detectar entrada/salida de bloques de código existentes
        if trimmed.startswith('```'):
            in_fence = not in_fence
            if in_sql and not in_fence:
                # Flush del bloque SQL antes de entrar en una valla
                sql_content = '\n'.join(current_block).strip()
                if sql_content:
                    token = next_code_token('CBLK')
                    code_map[token] = sql_content
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
                if trimmed.startswith('%%') and trimmed.endswith('%%'):
                    sql_content = '\n'.join(current_block).strip()
                    if sql_content:
                        token = next_code_token('CBLK')
                        code_map[token] = sql_content
                        new_lines.extend(['', token, ''])
                    in_sql = False
                    current_block.clear()
                    new_lines.append(line)
                    continue
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
                        token = next_code_token('CBLK')
                        code_map[token] = sql_content
                        new_lines.extend(['', token, ''])
                    in_sql = False
                    current_block.clear()
                    new_lines.append(line)
                else:
                    current_block.append(line)

    if in_sql:
        sql_content = '\n'.join(current_block).strip()
        if sql_content:
            token = next_code_token('CBLK')
            code_map[token] = sql_content
            new_lines.extend(['', token, ''])

    md_text = '\n'.join(new_lines)

    # ── Añadir hints de lenguaje a bloques ``` sin hint ───────────────────
    def _add_lang_hint(m: re.Match) -> str:
        existing_hint = m.group(1).strip()
        content       = m.group(2)
        if existing_hint:          # ya tiene hint, respetar
            return m.group(0)
        lang = _detect_code_lang(content)
        return f'```{lang}\n{content}```'

    md_text = re.sub(r'```(\w*)\n(.*?)```', _add_lang_hint, md_text, flags=re.DOTALL)

    # ── Limpieza de artefactos Freshdesk ──────────────────────────────────
    # Imagen rota del tipo [* ](url)
    md_text = re.sub(r'\[\s*\*\s*\]\((https?://[^\s)]+)\)', r'![]( \1)', md_text)
    # Imagen envuelta en enlace de Freshdesk/S3 → quitar enlace exterior
    md_text = re.sub(
        r'\[(!\[[^\]]*\]\([^)]+\)(?:\s+"[^"]*")?)\]\((https?://[^\s)]*?(?:amazonaws|freshdesk)[^\s)]*)\)',
        r'\1', md_text
    )

    # ── Normalización final ───────────────────────────────────────────────
    md_text = re.sub(r'\*\*\s*\*\*', '', md_text)
    md_text = re.sub(r'\*\*\s+\*\*', ' ', md_text)
    md_text = re.sub(r'\*\s*\*', '', md_text)
    md_text = re.sub(r'\s+\.', '.', md_text)
    md_text = re.sub(r'\s+,', ',', md_text)
    md_text = re.sub(r'\s+:', ':', md_text)
    md_text = re.sub(r'\s+;', ';', md_text)
    md_text = re.sub(r' {2,}', ' ', md_text)
    md_text = re.sub(r'\n ', '\n', md_text)
    md_text = re.sub(r' \n', '\n', md_text)
    md_text = re.sub(r'\n{3,}', '\n\n', md_text)

    # ── Restaurar bloques e inline code protegidos ────────────────────────
    for token, content in code_map.items():
        if token.startswith('%%CBLK_'):
            lang = _detect_code_lang(content)
            replacement = f'\n\n```{lang}\n{content}\n```\n\n'
        else:
            replacement = f'`{content}`'
        md_text = md_text.replace(token, replacement)

    md_text = re.sub(r'\n{3,}', '\n\n', md_text)
    md_text = _normalize_markdown_fences(md_text)
    return md_text.strip()


def apply_known_article_fixes(article_id: str, md_text: str) -> str:
    """Ajustes quirúrgicos para unos pocos artículos con HTML especialmente roto."""
    if not md_text:
        return md_text

    aid = str(article_id or '').strip()

    if aid == '154000130031':
        md_text = re.sub(
            r'(\*\*Ver c[oó]digo ejemplo\*\*)\n```\n\n```vb\n',
            r'\1\n\n```vb\n',
            md_text,
            flags=re.IGNORECASE,
        )

    if aid == '154000128795':
        md_text = re.sub(
            r'\n##### Autor: Daniel Ernesto Lutz Llano\n',
            '\n',
            md_text,
            flags=re.IGNORECASE,
        )
        md_text = re.sub(
            r'(-\s*Llamarla desde el ERP de una forma similar a la expuesta:\n+)(Set lObj = CreateObject \("[^"]*"\)\n+\s*lObj\.)',
            r'\1\n```vb\n\2\n```\n',
            md_text,
            flags=re.IGNORECASE,
        )
        md_text = md_text.replace(
            'End ClassPara llamarla desde el ERP se realizaría de la siguiente forma:',
            'End Class\n```\n\nPara llamarla desde el ERP se realizaría de la siguiente forma:'
        )
        md_text = md_text.replace(
            'lObj.crearPedido gcn, "00001", "0", 25En este ejemplo se mostraría un mensaje y se crearía un pedido.',
            'lObj.crearPedido gcn, "00001", "0", 25\n```\n\nEn este ejemplo se mostraría un mensaje y se crearía un pedido.'
        )
        md_text = re.sub(
            r'(Para llamarla desde el ERP se realizaría de la siguiente forma:\n)(Set lObj = CreateObject \("Prueba_ExternoNet\.Procesos"\)\nlObj\.mensaje\s*\nlObj\.crearPedido gcn, "00001", "0", 25)',
            r'\1\n```vb\n\2\n```',
            md_text,
            flags=re.IGNORECASE,
        )
        md_text = re.sub(r'\n{3,}', '\n\n', md_text).strip()

        link_match = re.search(r'(\n\[\]\([^)]+DLL%20externa[^)]*\s+"Teclas de acceso [^"]+"\)\s*)$', md_text, flags=re.IGNORECASE)
        if link_match and '##### Autor: Daniel Ernesto Lutz Llano' not in md_text:
            link_block = link_match.group(1)
            body = md_text[:-len(link_block)].rstrip()
            md_text = f'{body}\n\n##### Autor: Daniel Ernesto Lutz Llano\n\n{link_block.strip()}'

    return md_text


# ---------------------------------------------------------------------------
# Descarga de imágenes
# ---------------------------------------------------------------------------

def download_images_from_markdown(
    md_content: str,
    md_file_path: Path,
    images_out_dir: Path,
) -> str:
    """Descarga imágenes remotas y reemplaza URLs por rutas relativas locales."""
    images_out_dir.mkdir(parents=True, exist_ok=True)

    pattern = re.compile(r'!\[(.*?)\]\((https?://[^\s)]+)(?:\s+"[^"]*")?\)')
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
            img_filename = Path(parsed.path).name or 'image'
            safe_name = get_safe_filename(img_filename, 'image')

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
    counter: list[int],
) -> str:
    """Repara enlaces internos de Freshdesk apuntando a ficheros .md locales."""

    def get_relative_local_path(target_abs: str) -> str:
        return _relative_posix(current_file_path.parent, Path(target_abs))

    def resolve_target_path(article_id: str, link_text: str, url: str) -> Optional[str]:
        if article_id and article_id in article_paths:
            return article_paths[article_id]

        candidates: list[str] = []
        if link_text:
            candidates.extend(build_article_lookup_keys(link_text))
        if url:
            slug_m = re.search(r'/articles/\d+-([^/?#)]+)', url, re.IGNORECASE)
            if slug_m:
                candidates.extend(build_article_lookup_keys(slug_m.group(1)))

        for ck in dict.fromkeys(c for c in candidates if c):
            if ck in article_paths_by_title:
                return article_paths_by_title[ck]
            tokens = [t for t in ck.split(' ') if len(t) >= 3]
            if tokens:
                hits = [k for k in article_paths_by_title if all(t in k for t in tokens)]
                hits.sort(key=len)
                if len(hits) == 1:
                    return article_paths_by_title[hits[0]]

                # Fallback más permisivo: usar la coincidencia con mayor solape de tokens.
                ranked_hits: list[tuple[int, int, str]] = []
                token_set = set(tokens)
                for key in article_paths_by_title:
                    key_tokens = set(key.split(' '))
                    overlap = len(token_set & key_tokens)
                    if overlap:
                        ranked_hits.append((overlap, -len(key), key))
                ranked_hits.sort(reverse=True)
                if ranked_hits:
                    best_overlap = ranked_hits[0][0]
                    best = [key for overlap, _neg_len, key in ranked_hits if overlap == best_overlap]
                    if len(best) == 1 and best_overlap >= max(1, min(2, len(token_set))):
                        return article_paths_by_title[best[0]]
        return None

    # 1. Reemplazar enlaces Markdown con /articles/ID
    md_rx = re.compile(
        r'(?is)\[([^\]]*)\]\(([^)\s]*?/articles/(\d+)[^)\s]*?)(?:\s+"([^"]*)")?\)'
    )
    matches = list(md_rx.finditer(md_content))
    for m in reversed(matches):
        alt    = m.group(1)
        url    = m.group(2)
        art_id = m.group(3).strip()
        title  = html_lib.unescape(m.group(4) or '').strip()
        target = resolve_target_path(art_id, alt, url)
        if target:
            try:
                rel = get_relative_local_path(target)
                if title:
                    safe_title = title.replace('"', r'\"')
                    new_link = f'[{alt}]({rel} "{safe_title}")'
                else:
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
        r'\[\]\((https?://[^)\s]*?/articles/[^)\s]*)(?:\s+"[^"]*")?\)\s*\[([^\]]+)\]\(([^)]+?\.md)\)',
        r'[\2](\3)', md_content, flags=re.IGNORECASE
    )
    md_content = re.sub(
        r'\[\]\(([^)\s]+?\.md)(?:\s+"[^"]*")?\)\s*\[([^\]]+)\]\(([^)]+?\.md)\)',
        r'[\2](\3)', md_content, flags=re.IGNORECASE
    )

    # Reemplazar [](freshdesk) + texto siguiente
    empty_rx = re.compile(
        r'\[\]\(([^)\s]*?/articles/(\d+)[^)\s]*?)(?:\s+"[^"]*")?\)'
        r'((?:[^\s\[\]\(\),.;:!?][^,\n\r\)\]]{0,120}))'
    )
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
        r'\[\]\((https?://[^)\s]*?(?:freshdesk\.com|freshdesk\.es)[^)\s]*?/articles/[^)\s]*)(?:\s+"[^"]*")?\)',
        '', md_content, flags=re.IGNORECASE
    )

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
# Punto de entrada
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Genera solo articulos del autor objetivo y sanea su HTML antes de convertirlo a Markdown.'
    )
    parser.add_argument(
        '--connection-string',
        default='',
        help='ODBC Connection string de SQL Server'
    )
    parser.add_argument('--env-file', default='.env', help='Archivo .env del que cargar variables de entorno')
    parser.add_argument('--output-dir', default='.', help='Directorio base donde se generará la carpeta docs')
    parser.add_argument('--categories', nargs='*', default=[], help='Filtros de categoría')
    parser.add_argument('--category-contains', action='store_true', help='Usar "contiene" en lugar de exacto')
    parser.add_argument('--clean-output', action='store_true', help='Borrar output antes de generar')
    args = parser.parse_args()

    print('=====================================================')
    print(' Generando estructura MkDocs solo para articulos del autor objetivo ')
    print('=====================================================')

    output_dir  = Path(args.output_dir)
    env_file = Path(args.env_file)
    docs_folder = output_dir / 'docs'
    images_folder = docs_folder / 'docs_assets' / 'images'
    state_path = get_state_path(output_dir)
    generation_state = load_generation_state(output_dir)
    incremental_mode = state_path.exists()

    if incremental_mode:
        last_generated_at = generation_state.get('meta', {}).get('last_generated_at', '')
        print(f'[*] Autor: modo incremental activo desde {last_generated_at or "(sin fecha válida)"}')
    else:
        print('[*] Autor: no existe generation_state.json; se evaluarán todos los artículos del filtro.')

    if args.clean_output and docs_folder.exists():
        import shutil
        shutil.rmtree(docs_folder)
    docs_folder.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    connection_string = resolve_connection_string(args.connection_string, env_file)
    conn = pyodbc.connect(connection_string)
    cursor = conn.cursor()

    enlaces_reparados = [0]  # lista para mutabilidad en funciones anidadas

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
            if cid:
                dic_categorias[cid] = get_safe_filename(name, f'Categoria_{cid}')
                dic_categorias_raw[cid] = str(name)
                dic_categorias_product[cid] = str(product_val).strip()
        except Exception:
            pass

    # Filtrar categorías
    categories = args.categories
    if not categories:
        prompt = input('Introduce una categoría exacta (o parte si usas --category-contains). Vacío = todas: ').strip()
        if prompt:
            categories = [c.strip() for c in prompt.split(',') if c.strip()]

    selected_ids: list[str] = []
    if categories:
        for f in categories:
            for cid, name in dic_categorias_raw.items():
                if args.category_contains:
                    match = f.lower() in name.lower()
                else:
                    match = name.lower() == f.lower()
                if match and cid not in selected_ids:
                    selected_ids.append(cid)

        if not selected_ids:
            conn.close()
            sys.exit(f'No se encontró ninguna categoría que coincida con: {", ".join(categories)}')

        selected_names = [dic_categorias_raw[cid] for cid in selected_ids]
        print(f'[*] Categorías seleccionadas: {", ".join(selected_names)}')

    # ==========================================
    # 2. CARGAR CARPETAS
    # ==========================================
    print('[*] Leyendo Carpetas...')
    dic_carpetas: dict[str, str] = {}
    cursor.execute("SELECT JSONDATA FROM [dbo].[freshdesk_folders] WHERE JSONDATA IS NOT NULL")
    for row in cursor.fetchall():
        try:
            j = json.loads(row[0])
            fid  = str(j.get('Id') or j.get('id') or '')
            name = j.get('Name') or j.get('name') or ''
            if fid:
                dic_carpetas[fid] = get_safe_filename(name, f'Carpeta_{fid}')
        except Exception:
            pass

    # ==========================================
    # 3. CARGAR Y FILTRAR ARTICULOS OBJETIVO
    # ==========================================
    print('[*] Filtrando artículos del autor objetivo...')
    target_articles: list[dict] = []
    count_skipped_non_target_author = 0

    cursor.execute("SELECT JSONDATA FROM [dbo].[freshdesk_articles] WHERE JSONDATA IS NOT NULL")
    for row in cursor.fetchall():
        try:
            raw = row[0]
            if not raw or not raw.strip():
                continue
            articulo = json.loads(raw)

            art_id = articulo.get('Id') or articulo.get('id')
            if art_id is None:
                continue

            cat_id = str(articulo.get('CategoryId') or articulo.get('category_id') or '')
            if selected_ids and cat_id not in selected_ids:
                continue

            desc = articulo.get('Description') or articulo.get('description') or ''
            if not is_target_author_article(str(desc)):
                count_skipped_non_target_author += 1
                continue

            if incremental_mode:
                folder_id = str(articulo.get('FolderId') or articulo.get('folder_id') or '')
                title = articulo.get('Title') or articulo.get('title') or ''
                updated_at = str(articulo.get('updated_at') or articulo.get('UpdatedAt') or '')
                clean_title = get_safe_filename(title, f'Articulo_{art_id}')
                md_path = docs_folder / dic_categorias.get(cat_id, 'Categoria_Desconocida') / dic_carpetas.get(folder_id, 'Carpeta_Desconocida') / f'{clean_title}.md'
                if not should_generate_article(
                    generation_state,
                    str(art_id),
                    updated_at,
                    md_path,
                ):
                    continue

            target_articles.append(articulo)
        except Exception:
            pass

    # ==========================================
    # 4. PRE-CALCULAR RUTAS DE ARTÍCULOS
    # ==========================================
    print('[*] Pre-calculando rutas para enlaces internos...')
    planned_article_paths = build_article_output_plan(
        target_articles,
        docs_folder,
        dic_categorias,
        dic_carpetas,
    )
    dic_articulos_rutas: dict[str, str] = {}
    dic_articulos_rutas_por_titulo: dict[str, str] = {}

    for j in target_articles:
        try:
            art_id = j.get('Id') or j.get('id')
            if art_id is None:
                continue
            cat_id    = str(j.get('CategoryId') or j.get('category_id') or '')
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

            for title_key in build_article_lookup_keys(title):
                if title_key not in dic_articulos_rutas_por_titulo:
                    dic_articulos_rutas_por_titulo[title_key] = path_abs
        except Exception:
            pass

    # ==========================================
    # 5. PROCESAR ARTÍCULOS
    # ==========================================
    print('[*] Generando archivos .md del autor objetivo...')
    count_ok = 0
    count_err = 0
    count_html_patched = 0

    for articulo in target_articles:
        try:
            art_id = articulo.get('Id') or articulo.get('id')
            if art_id is None:
                continue

            folder_id = str(articulo.get('FolderId') or articulo.get('folder_id') or '')
            cat_id    = str(articulo.get('CategoryId') or articulo.get('category_id') or '')

            cat_name    = dic_categorias.get(cat_id, 'Categoria_Desconocida')
            folder_name = dic_carpetas.get(folder_id, 'Carpeta_Desconocida')

            title = articulo.get('Title') or articulo.get('title') or ''
            desc  = articulo.get('Description') or articulo.get('description') or ''
            updated_at = str(articulo.get('updated_at') or articulo.get('UpdatedAt') or '')

            out_dir_art = docs_folder / cat_name / folder_name
            out_dir_art.mkdir(parents=True, exist_ok=True)
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

            patched_desc = sanitize_target_author_html(str(desc))
            if patched_desc != str(desc):
                count_html_patched += 1

            md_content = convert_html_to_markdown(patched_desc)
            md_content = apply_known_article_fixes(str(art_id), md_content)
            md_content = download_images_from_markdown(md_content, md_path, images_folder)
            md_content = fix_internal_links(
                md_content, md_path,
                dic_articulos_rutas, dic_articulos_rutas_por_titulo,
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
            if count_ok % 500 == 0:
                print(f'    -> {count_ok} generados...')

        except Exception as e:
            count_err += 1
            continue

    cursor.close()
    conn.close()

    print('\n=====================================================')
    print(f' Finalizado: {count_ok} artículos .md objetivo en sus carpetas. ')
    print(f' HTML saneado con el parche: {count_html_patched}')
    print(f' Enlaces internos reparados a formato local: {enlaces_reparados[0]}')
    print('=====================================================')


if __name__ == '__main__':
    main()
