import "beercss";
import "material-dynamic-colors";
import "../css/theme.css";
import "../css/style.css";

export function toggleMode() {
    let currentMode = localStorage.getItem("mode") || "dark";
    let newMode = currentMode === "dark" ? "light" : "dark";
    localStorage.setItem("mode", newMode);
    ui("mode", newMode);
    updateIcon(newMode);
    updateImageSource();
};

function updateImageSource() {
    const mode = localStorage.getItem('mode') || 'light';
    const images = document.querySelectorAll('img[id^="recording-card-image"]');
    images.forEach(image => {
        image.src = mode === 'dark' ? '/static/hbni_logo_dark.png' : '/static/hbnilogo.png';
    });
}

function updateIcon(mode) {
    const iconElements = document.querySelectorAll('#toggle-theme i');
    iconElements.forEach(iconElement => {
        iconElement.textContent = mode === "dark" ? "light_mode" : "dark_mode";
    });
};

function loadAnimationStyleSheet() {
    const style = document.createElement("style");
    style.textContent = `
    html,
    body,
    div,
    article,
    p,
    h1,
    h2,
    h3,
    h4,
    h5,
    h6,
    ul,
    li,
    span,
    a,
    button,
    input,
    textarea,
    select,
    details,
    summary,
    footer,
    blockquote,
    pre,
    code,
    .field {
        transition: background-color var(--speed3) ease-in-out, color var(--speed1) ease;
    }
    dialog{
        transition: background-color var(--speed3) ease-in-out, color var(--speed1) ease, all var(--speed3);
    }
  `.trim();
    document.head.appendChild(style);
}

export function loadTheme(){
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const theme = prefersDark ? 'dark' : 'light';
    // const theme = localStorage.getItem('mode') || 'dark';
    ui('mode', theme);
    updateIcon(theme);
    updateImageSource();
    setTimeout(() => {
        loadAnimationStyleSheet();
    }, 100);
    document.body.classList.remove("hidden");
}

window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e => {
    const newTheme = e.matches ? 'dark' : 'light';
    ui('mode', newTheme);
    updateIcon(newTheme);
    updateImageSource();
});