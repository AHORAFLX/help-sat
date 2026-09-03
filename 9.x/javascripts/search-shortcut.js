// Intercepts Ctrl+F / Cmd+F to open this site's own search instead of the browser's native find bar.
document.addEventListener("keydown", function (event) {
    var key = event.key ? event.key.toLowerCase() : "";
    if ((event.ctrlKey || event.metaKey) && key === "f") {
        var searchToggle = document.getElementById("__search");
        if (!searchToggle) return;

        event.preventDefault();
        searchToggle.checked = true;

        var searchInput = document.querySelector('[data-md-component="search-query"]');
        if (searchInput) {
            searchInput.focus();
        }
    }
});
