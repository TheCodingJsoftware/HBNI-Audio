import { loadTheme, toggleMode } from "/static/js/theme.js";

document.addEventListener('DOMContentLoaded', function () {
    loadTheme();
    document.getElementById('toggle-theme').addEventListener('click', toggleMode);
});
