"""
repair_links_pipeline.py
========================
Pipeline consolidado para la reparación y validación de enlaces en la documentación Markdown.
Une las funcionalidades de finalize_links.py, definitive_fix.py, fix_links.py y validate_erp.py.
"""
import os
import re
import argparse
import unicodedata
from pathlib import Path
from urllib.parse import unquote, quote

# =========================================================================
# 1. Utilidades y Configuración de Rutas
# =========================================================================

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DOCS_DIR = (BASE_DIR / 'docs').resolve()
UNFIXABLE_LOG = (BASE_DIR / 'unfixable_links_log.txt').resolve()
VALIDATION_LOG = (BASE_DIR / 'docs_validation_log.txt').resolve()

def normalize_name(text: str) -> str:
    if not text: return ""
    text = unquote(text).lower()
    if text.endswith('.md'): text = text[:-3]
    normalized = unicodedata.normalize('NFD', text)
    result = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
    result = re.sub(r'[^a-z0-9]+', ' ', result).strip()
    return result

def get_relative_posix(from_dir: Path, to_file: Path) -> str:
    rel = os.path.relpath(str(to_file), str(from_dir))
    return rel.replace('\\', '/').replace(' ', '%20')

def robust_replace(file_path: Path, old_snippet: str, new_path: str):
    if not file_path.exists(): return False
    content = file_path.read_text(encoding='utf-8')
    changed = False
    
    if old_snippet in content:
        content = content.replace(old_snippet, new_path)
        changed = True
    else:
        # Búsqueda por regex ignorando encoding de espacios
        pattern = re.escape(old_snippet).replace(r'\%20', r'(?:%20|\s+)').replace(r'\ ', r'(?:%20|\s+)')
        if re.search(pattern, content):
            content = re.sub(pattern, new_path, content)
            changed = True

    if changed:
        file_path.write_text(content, encoding='utf-8')
    return changed

# =========================================================================
# 2. Fase de Arreglos Manuales y Específicos (Heredado de finalize/definitive)
# =========================================================================

def phase_manual_fixes(docs_dir: Path):
    print("[*] Iniciando Fase 1: Arreglos Manuales Específicos...")
    
    # 1. Sebastian HR
    robust_replace(
        docs_dir / "Sebastian HR by flexygo" / "Primeros pasos" / "Configuración Inicial Sebastian HR.md",
        "../../Flexygo/Licenciamiento/¿Cómo puedo activar mi licencia.md",
        "../../Flexygo/Licenciamiento/¿Cómo puedo activar mi licencia.md"
    )

    # 2. Principales Novedades - ICONOS
    f1 = docs_dir / "Producto - Versiones" / "Versión 5.0" / "Principales Novedades AHORA ERP 5 (HighLights).md"
    if f1.exists():
        content = f1.read_text(encoding='utf-8')
        # Limpiar cualquier rastro de .md).md)
        content = re.sub(r'\[aquí\]\(\.\./\.\./ERP - Configuración ADMON/Admon/Admon - Gestión de ICONOS \(v\.5\)\.md\)(\.md\)\.?)*', 
                         r'[aquí](../../ERP - Configuración ADMON/Admon/Admon - Gestión de ICONOS (v.5).md)', content)
        # Fix truncated link from finalize_links
        pattern = re.escape("../../ERP%20-%20Configuración%20ADMON/Admon/Admon%20-%20Gestión%20de%20ICONOS%20(v.5").replace(r'\%20', r'(?:%20|\s+)')
        content = re.sub(pattern, "../../ERP - Configuración ADMON/Admon/Admon - Gestión de ICONOS (v.5).md", content)
        f1.write_text(content, encoding='utf-8')

    # 3. ERP. Precios de Transporte
    f2 = docs_dir / "ERP_ahoraSCO" / "Ventas_ahoraSCO" / "ERP. Precios de Transporte.md"
    if f2.exists():
        content = f2.read_text(encoding='utf-8')
        # Asegurar que el link es el correcto
        content = re.sub(r'\[([^\]]+)\]\(ERP\. Precios de Transporte con intervalos de Unidades, Pesos o Bultos.*?\)', 
                         r'[\1](ERP. Precios de Transporte con intervalos de Unidades, Pesos o Bultos (EN PROCESO).md)', content)
        # Robust replace for truncated version
        robust_replace(f2, "ERP.%20Precios%20de%20Transporte%20con%20intervalos%20de%20Unidades,%20Pesos%20o%20Bultos%20(EN%20PROCESO", 
                       "ERP. Precios de Transporte con intervalos de Unidades, Pesos o Bultos.md")
        f2.write_text(content, encoding='utf-8')

    # 4. DevExpress Reports
    f3 = docs_dir / "ERP" / "Ley Antifraude" / "ERP - Añadir componente QR Veri-Factu al listado factura.md"
    if f3.exists():
        content = f3.read_text(encoding='utf-8')
        content = re.sub(r'\[([^\]]+)\]\(\.\./Reporting/DevExpress Reports - Conversión de informes desde Crystal Reports \(\.rpt.*?\)', 
                         r'[\1](../Reporting/DevExpress Reports - Conversión de informes desde Crystal Reports (.rpt).md)', content)
        # Robust replace for truncated version
        robust_replace(f3, "../Reporting/DevExpress%20Reports%20-%20Conversión%20de%20informes%20desde%20Crystal%20Reports%20(.rpt",
                       "../Reporting/DevExpress Reports - Conversión de informes desde Crystal Reports (.rpt).md")
        f3.write_text(content, encoding='utf-8')

    # 5. Malformed URL Ley Antifraude
    robust_replace(
        docs_dir / "ERP" / "Ley Antifraude" / "FAQ - Ley Antifraude - ¿Puedo emitir una factura con fecha de expedición distinta a la actual-.md",
        "?https%3A//sede.agenciatributaria.gob.es",
        "https://sede.agenciatributaria.gob.es"
    )

    print("[*] Fase 1 completada.")

# =========================================================================
# 3. Fase de Reparación Difusa (Heredado de fix_links)
# =========================================================================

def phase_fuzzy_repair(docs_dir: Path, log_path: Path):
    print("[*] Iniciando Fase 2: Reparación Difusa de Enlaces...")
    
    file_map = {} 
    all_md_files = list(docs_dir.rglob('*.md'))
    for p in all_md_files:
        norm = normalize_name(p.name)
        if norm not in file_map:
            file_map[norm] = []
        file_map[norm].append(p)
    
    print(f'[*] Mapeados {len(all_md_files)} archivos.')

    broken_count = 0
    fixed_count = 0
    unfixable = []
    link_pattern = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
    
    for md_file in all_md_files:
        content = md_file.read_text(encoding='utf-8')
        new_content = content
        matches = list(link_pattern.finditer(content))
        if not matches: continue
        
        changed = False
        for m in reversed(matches):
            text = m.group(1)
            url = m.group(2).strip()
            
            if url.startswith(('http', 'mailto', 'tel', '#')): continue
            
            url_clean = unquote(url).split('#')[0]
            if not url_clean: continue
            
            target_path = (md_file.parent / url_clean).resolve()
            
            if not target_path.exists():
                broken_count += 1
                link_filename = Path(url_clean).name
                norm_link = normalize_name(link_filename)
                
                found = False
                if norm_link in file_map:
                    candidates = file_map[norm_link]
                else:
                    if len(norm_link) >= 10:
                        prefix_hits = [k for k in file_map if k.startswith(norm_link) or norm_link.startswith(k)]
                        candidates = []
                        for ph in prefix_hits:
                            candidates.extend(file_map[ph])
                    else:
                        candidates = []

                if candidates:
                    if len(candidates) == 1:
                        new_rel = get_relative_posix(md_file.parent, candidates[0])
                        anchor = url.split('#')[1] if '#' in url else ''
                        if anchor: new_rel += '#' + anchor
                        
                        replacement = f'[{text}]({new_rel})'
                        new_content = new_content[:m.start()] + replacement + new_content[m.end():]
                        fixed_count += 1
                        changed = True
                        found = True
                    else:
                        unfixable.append(f"Archivo: {md_file.relative_to(docs_dir)}\n  Enlace roto: {url}\n  Causa: Ambiguo, múltiples candidatos: {[str(c.relative_to(docs_dir)) for c in candidates]}\n")
                        found = True 

                if not found:
                    unfixable.append(f"Archivo: {md_file.relative_to(docs_dir)}\n  Enlace roto: {url}\n  Causa: No se encontró ningún archivo con nombre similar.\n")

        if changed:
            md_file.write_text(new_content, encoding='utf-8')

    print(f'[*] Fase 2 terminada.')
    print(f'    Enlaces detectados como rotos: {broken_count}')
    print(f'    Enlaces reparados: {fixed_count}')

    with open(log_path, 'w', encoding='utf-8') as f:
        f.write("================ ENLACES NO REPARADOS (BÚSQUEDA DIFUSA) ================\n\n")
        for line in unfixable:
            f.write(line + "\n")
    print(f'[*] Log de casos no resueltos en: {log_path}')

# =========================================================================
# 4. Fase de Validación (Heredado de validate_erp)
# =========================================================================

def phase_validation(docs_dir: Path, log_path: Path):
    print("[*] Iniciando Fase 3: Validación Final...")
    broken_links = []
    
    link_pattern = re.compile(r'\[([^\]]+)\]\(((?:[^()]|\([^()]*\))+)\)')
    code_block_pattern = re.compile(r'```.*?```', re.DOTALL)
    inline_code_pattern = re.compile(r'`[^`]+`')

    files = list(docs_dir.rglob('*.md'))
    for md_file in files:
        content = md_file.read_text(encoding='utf-8')
        clean_content = code_block_pattern.sub('CODE_BLOCK_PLACEHOLDER', content)
        clean_content = inline_code_pattern.sub('INLINE_CODE_PLACEHOLDER', clean_content)
        
        for match in link_pattern.finditer(clean_content):
            text = match.group(1)
            url = match.group(2).strip()
            
            if url.startswith(('http://', 'https://', 'mailto:', 'tel:', '#')): continue
            
            if '#' in url:
                url = url.split('#')[0]
                if not url: continue

            url_decoded = unquote(url)
            target_path = (md_file.parent / url_decoded).resolve()
            
            if not target_path.exists():
                if not target_path.suffix: continue # Ignorar técnicos sin extensión
                
                broken_links.append({
                    'file': md_file.relative_to(docs_dir),
                    'link': url,
                    'text': text,
                    'cause': f'Archivo no encontrado: {target_path}'
                })

    with open(log_path, 'w', encoding='utf-8') as f:
        f.write("================ REPORT DE VALIDACION DE ENLACES ================\n\n")
        f.write(f"Directorio: {docs_dir}\n\n")
        if not broken_links:
            f.write("No se encontraron enlaces rotos.\n")
        else:
            f.write(f"-- {len(broken_links)} ENLACES ROTOS --\n")
            for item in broken_links:
                f.write(f"Archivo: {item['file']}\n")
                f.write(f"  Texto: {item['text']}\n")
                f.write(f"  Enlace: {item['link']}\n")
                f.write(f"  Causa: {item['cause']}\n\n")

    print(f'[*] Fase 3 completada. Se han encontrado {len(broken_links)} enlaces rotos.')
    print(f'[*] Reporte guardado en: {log_path}')
    return len(broken_links)

# =========================================================================
# Main Entry Point
# =========================================================================

def main():
    parser = argparse.ArgumentParser(description='Pipeline de reparación y validación de enlaces.')
    parser.add_argument('--docs-dir', type=str, default=str(DEFAULT_DOCS_DIR), help='Directorio de documentación')
    parser.add_argument('--skip-fuzzy', action='store_true', help='Saltar reparación difusa')
    parser.add_argument('--skip-validation', action='store_true', help='Saltar validación final')
    args = parser.parse_args()

    docs_dir = Path(args.docs_dir).resolve()
    if not docs_dir.exists():
        print(f"[ERROR] El directorio {docs_dir} no existe.")
        return

    # Ejecutar Fases
    phase_manual_fixes(docs_dir)
    
    if not args.skip_fuzzy:
        phase_fuzzy_repair(docs_dir, UNFIXABLE_LOG)
        
    if not args.skip_validation:
        phase_validation(docs_dir, VALIDATION_LOG)

    print("\n[OK] Pipeline finalizado con éxito.")

if __name__ == '__main__':
    main()
