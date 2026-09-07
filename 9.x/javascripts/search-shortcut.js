// Intercepts Ctrl+K / Cmd+K to open this site's own search.
document.addEventListener("keydown", function (event) {
    var key = event.key ? event.key.toLowerCase() : "";
    if ((event.ctrlKey || event.metaKey) && key === "k") {
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
