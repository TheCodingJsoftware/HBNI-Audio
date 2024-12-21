document.addEventListener('DOMContentLoaded', function () {
    let savedMode = localStorage.getItem("mode") || "light";
    ui("mode", savedMode);
    document.documentElement.classList.toggle("dark", savedMode === "dark");
});
