const mode = () => {
    let currentMode = localStorage.getItem("mode") || "dark";
    let newMode = currentMode === "dark" ? "light" : "dark";
    localStorage.setItem("mode", newMode); // Save mode to localStorage
    ui("mode", newMode);
    updateIcon(newMode);
    updateImageSource();
    document.documentElement.classList.toggle("dark", newMode === "dark");
};

function updateImageSource() {
    const mode = localStorage.getItem('mode') || 'light';
    const images = document.querySelectorAll('img[id^="recording-card-image"]');
    images.forEach(image => {
        image.src = mode === 'dark' ? '/static/hbni_logo_dark.png' : '/static/hbnilogo.png';
    });
}

const updateIcon = (mode) => {
    const iconElements = document.querySelectorAll('#toggle-theme i');
    iconElements.forEach(iconElement => {
        iconElement.textContent = mode === "dark" ? "light_mode" : "dark_mode";
    });
};

function searchAndFilter() {
    const searchInput = document.getElementById('search');
    const query = searchInput.value.toLowerCase();
    const articles = document.querySelectorAll('#contents');
    let foundArticle = false;

    articles.forEach(function (article) {
        const articleVersions = article.querySelectorAll('#article-version');
        articleVersions.forEach(function (articleVersion) {
            const name = articleVersion.getAttribute('data-name').toLowerCase();
            if (name.includes(query)) {
                articleVersion.style.display = 'block';
                foundArticle = true;
            } else {
                articleVersion.style.display = 'none';
            }
        });


        const noResults = document.querySelector('.no-results');
        if (foundArticle) {
            noResults.style.display = 'none';
        } else {
            noResults.style.display = 'block';
        }
    });
}

function adjustDialogForScreenSize() {
    const infoDialog = document.getElementById('info-dialog');
    const downloadDialog = document.getElementById('download-dialog');
    if (window.innerWidth <= 600) {
        infoDialog.classList.add('max');
        downloadDialog.classList.add('bottom');
    } else {
        downloadDialog.classList.remove('bottom');
        infoDialog.classList.remove('max');
    }
}

function adjustDetailsForScreenSize() {
    const detailsElements = document.querySelectorAll('details');
    if (window.innerWidth <= 600) { // Mobile view threshold
        detailsElements.forEach(details => details.removeAttribute('open'));
    } else {
        detailsElements.forEach(details => details.setAttribute('open', ''));
    }
}

document.addEventListener('DOMContentLoaded', function () {
    let savedMode = localStorage.getItem("mode") || "light";
    ui("mode", savedMode);
    updateIcon(savedMode);
    document.documentElement.classList.toggle("dark", savedMode === "dark");
    const searchInput = document.getElementById('search');

    searchInput.addEventListener('input', searchAndFilter);
    updateImageSource();
    adjustDialogForScreenSize();
    adjustDetailsForScreenSize();

    window.addEventListener('resize', () => {
        adjustDialogForScreenSize();
        adjustDetailsForScreenSize();
    });
});
