const FH_CULTURES = new Object(); //The object with every culture translations
const LANGUAGES = ['en', 'es'];

let navigation_dialog;
addEventListener("DOMContentLoaded", () => { 
    navigation_dialog = document.getElementById('navigation-dialog');
    navigation_dialog.querySelector('label').innerText = translate('flexygo_URL_modal_title');

    // We check if we are on flexygo and add a class to the document so we can style accordingly
    if (isAFlexy()) {
        document.documentElement.classList.add('in-flexygo');
    }

    //We restore the palette from local storage, so it persists even on version change
    restorePaletteFromStorage();

    //We listen for changes on the palette selector to update the palette in local storage
    document.querySelectorAll('input[name="__palette"]').forEach(input => {
        input.addEventListener('change', (e) => {
            const palette = e.target.getAttribute('data-md-color-scheme');
            localStorage.setItem('fh-palette', palette === 'default' ? 'light' : 'dark');
        });
    });
});

function changeLanguage(new_language) {
    const base_path = getBasePath();
    const [true_base_path, relative_path] = splitBase(base_path);

    // We divide the path into segments and get the first from it, so we can get the current language
    const path_segments = relative_path.split('/').filter(Boolean);
    const fist_segment = path_segments[0] || '';
    const current_language = LANGUAGES.includes(fist_segment) ? fist_segment : DEFAULT_LANGUAGE;

    // We stop the redirection if the language is the same as the current
    if (new_language === current_language || (new_language === '' && current_language === DEFAULT_LANGUAGE)) {
        return;
    }

    // Build new relative path segments without the locale segment (if present)
    const path_segments_no_language = LANGUAGES.includes(fist_segment) ? path_segments.slice(1) : path_segments;

    // We create the new relative path and add the new language if it's not the default one
    let new_relative_path; 
    if(new_language && new_language !== DEFAULT_LANGUAGE) {
        new_relative_path = [new_language, ...path_segments_no_language].join('/')
    } else {
        new_relative_path = path_segments_no_language.join('/');
    }

    // Depending on if the original path ended in an slash or not, we keep it so later we can add it to the new path (thought for strict urls)
    const keep_trailing_slash = relative_path.endsWith('/') || path_segments_no_language.length === 0;

    // We build the new URL and redirect to it
    const new_path = true_base_path + '/' + new_relative_path + (keep_trailing_slash ? '/' : '');
    const new_url = new_path.replace(/\/{2,}/g, '/') + window.location.search + window.location.hash; //We avoid double / with the regex and also mantain querys and hashes

    window.location.href = new_url;
}

// We look for any <link> that points into /main-flexygo-styles.css and grab that url from before stylesheets so that will know the base path
// We do it with main-flexygo-styles.css because /docs_assets/ is saved in a different place
function getBasePath() {
    const link_element = document.querySelector('link[href*="/main-flexygo-styles.css"]');
    if (!link_element) return '';
    try {
        // We get the prefix up to (but not including) /docs_assets/ and remove the last / if present 
        const url = new URL(link_element.href, window.location.origin);
        const base_path = url.pathname.split('/stylesheets/')[0];
        
        return base_path.endsWith('/') ? base_path.slice(0, -1) : base_path;
    } catch {
        return '';
    }
}

function splitBase(base_path) {
    if (base_path) {
        if (location.pathname.startsWith(base_path + '/')) 
            return [base_path, location.pathname.slice(base_path.length)];
        if (location.pathname === base_path) 
            return [base_path, '/'];
    }
    return ['', location.pathname];
}

let current_navigation_json;
function navigateToFlexy(json, ctrlKey_pressed) {
    current_navigation_url = json;

    if (!this.isAFlexy()) {
        if (ctrlKey_pressed) {
            _nav(document.getElementById('navigation-dialog-flexy-url').value);
        } else {
            navigation_dialog.showModal();

            //We focus the end of the input
            const dialog_input = navigation_dialog.querySelector('input');
            const input_length = dialog_input.value.length;
            dialog_input.setSelectionRange(input_length, input_length);
        }

        return;
    }

    _nav();
}

function isAFlexy() {
    const is_mkdocs = (window.location.hostname === 'localhost' || 
                        window.location.hostname === '127.0.0.1') &&
                        window.location.port === '8000';
    return !is_mkdocs && !window.location.href.includes('ayuda.ahora.es');
}

function _nav(url) {
    if (!url) {
        //We remove /docs from the path if we are in flexygo to get the correct base path
        if (isAFlexy()) {
            url = window.location.href;
            url = url.slice(0, url.indexOf('/docs')) + '/Index#' + btoa(JSON.stringify(current_navigation_url));
        } else {
            url += getBasePath() + '/Index#' + btoa(JSON.stringify(current_navigation_url));
        }
    } else {
        if (!url.endsWith('/')) {
            url += '/';
        }

        url += 'Index#' + btoa(JSON.stringify(current_navigation_url));
    }

    window.open(url, '_blank');
    navigation_dialog.close();
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showDialog(translate('copied'));
    }); 
}

function showDialog(text) {
    const md_dialog = document.querySelector('.md-dialog');
    md_dialog.querySelector('.md-dialog__inner').innerText = text;
    md_dialog.classList.add('md-dialog--active');
    setTimeout(() => {
        md_dialog.classList.remove('md-dialog--active');
    }, 2300);
}

function getLanguage() {
    if (window.location.href.includes('/es/'))
        return 'es';

    return 'en';
}

function toggleGraphsFilter(button) {
    const graphs = document.querySelectorAll('.filtered-graph, .unfiltered-graph');

    if (graphs[0].classList.contains('filtered-graph')) {
        graphs.forEach(graph => {
            graph.src = graph.src.replace('_filtered.png', '.png');

            graph.classList.remove('filtered-graph');
            graph.classList.add('unfiltered-graph');

            button.innerText = translate('filter_charts');
        });

        return;
    }

    graphs.forEach(graph => {
        graph.src = graph.src.replace('.png', '_filtered.png');

        graph.classList.remove('unfiltered-graph');
        graph.classList.add('filtered-graph');

        button.innerText = translate('unfilter_charts');
    });
}

function toggleCollapsable(element) {
    const collapsable_element = document.querySelector(element.dataset.target);
    collapsable_element.classList.toggle('collapsed');
    element.classList.toggle('icon-rotate-90');
}

function translate(key) {
    const lang = getLanguage();
    return FH_CULTURES[lang][key] || key;
}

function getElementsWithCertainText(starting_element, text) {
    const walker = document.createTreeWalker(
        starting_element,
        NodeFilter.SHOW_TEXT,
        null,
        false
    );
    
    let node, matches = [];
    while (node = walker.nextNode()) {
        if (node.textContent.includes(text)) {
            matches.push(node.parentElement);
        }
    }

    return matches;
}

function isOnIframe() {
    return window.location !== window.parent.location;
}

function splitAtLastOccurrence(text, character) {
    const index = text.lastIndexOf(character);
    return [text.substring(0, index), text.substring(index + 1)];
}

async function urlExists(url) {
    try {
        const response = await fetch(url, { method: 'HEAD' });
        return response.ok;
    } catch {
        return false;
    }
}

function restorePaletteFromStorage() {
    const current_palette = localStorage.getItem('fh-palette');
    if (current_palette) {
        const palette_button = document.querySelector(`[data-md-component="palette"] [title="Switch to ${current_palette} mode"]`);
        palette_button?.click();
    } else {
        localStorage.setItem('fh-palette', 'default');
    }
}