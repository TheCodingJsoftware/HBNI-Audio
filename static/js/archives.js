import { loadTheme, toggleMode } from "/static/js/theme.js";

let allItems = [];
let currentPage = 1;
const itemsPerPage = 20;

// references to pagination elements
let contentsContainer;
let prevPageBtn;
let nextPageBtn;
let pageNumbersContainer;

function searchAndFilter() {
    const searchInput = document.getElementById('search');
    const query = searchInput.value.toLowerCase();
    const articles = document.querySelectorAll('#article-version');
    let foundArticle = false;

    articles.forEach(function (article) {
        const name = article.getAttribute('data-name').toLowerCase();
        if (name.includes(query)) {
            article.style.display = 'block';
            foundArticle = true;
        } else {
            article.style.display = 'none';
        }
    });


    const noResults = document.querySelector('.no-results');
    if (foundArticle) {
        noResults.style.display = 'none';
    } else {
        noResults.style.display = 'block';
    }
}

function closeAllDetails() {
    const detailsElements = document.querySelectorAll('details');
    detailsElements.forEach(details => details.removeAttribute('open'));
}

function getArchiveBroadcastElement(itemData, index){
    const groupName = itemData.groupName;
    const article = document.createElement('article');
    article.className = 'small-margin round no-padding s12 m6 l6 fade-in';
    article.id = 'article-version';
    article.dataset.name = itemData.filename.replace('_', ':').replace('.mp3', '');

    const prefetch = (url) => {
        const link = document.createElement('link');
        link.rel = 'prefetch';
        link.href = url;
        document.head.appendChild(link);
    };

    const isNewBadge = (
        groupName.includes("Days") ||
        groupName.includes("Yesterday") ||
        groupName.includes("Today")
    );

    let downloadLink = itemData.download_link;
    let downloadIcon = 'download';
    let downloadText = 'Download';
    if (downloadLink.includes("play_recording")) {
        downloadIcon = 'play_arrow';
        downloadText = 'Play';
        downloadLink = `/play_recording/${itemData.filename}`;
    } else if (downloadLink.includes("mega") || downloadLink.includes("google")) {
        downloadIcon = 'globe';
    }
    const newBadgeHtml = isNewBadge ? `<div class="badge none">New</div>` : '';

    article.innerHTML = `
    <div class="padding">
        <div class="row top-align">
            <h6 class="small bold max">
                ${itemData.description}
            </h6>
            <span>${newBadgeHtml}</span>
        </div>
        <nav class="wrap no-space">
            <button class="chip tiny-margin round">
                <i>home_pin</i>
                <span>${itemData.host.replace(/\//g, '')
                    .replace(/^./, char => char.toUpperCase())}</span>
            </button>
            <button class="chip tiny-margin round">
                <i>web_traffic</i>
                <span>${itemData.visit_count}</span>
                <div class="tooltip bottom">
                    <span class="left-align">
                    Latest Visit:<br>${itemData.latest_visit}
                    </span>
                </div>
            </button>
            <button class="chip tiny-margin round">
                <i>schedule</i>
                <span>${itemData.formatted_length}</span>
            </button>
            <button class="chip tiny-margin round">
                <i>event</i>
                <span>${itemData.uploaded_days_ago}</span>
                <div class="tooltip bottom">
                    <span class="left-align">
                    ${itemData.date.replace('_', ':')}
                    </span>
                </div>
            </button>
        </nav>
        <nav class="grid">
            <button class="${downloadLink.includes("play_recording") ? "s6" : "s12"}" id="play-button-${index}">
                <i>${downloadIcon}</i>
                <span>${downloadText}</span>
            </button>
            <!-- if "play_recording" is in the URL -->
            ${downloadLink.includes("play_recording")
            ?`
            <button class="s6 border" id="download-button-${index}">
                <i>download</i>
                <span>Download</span>
            </button>
            `
            : ""}
        </nav>
    </div>
    `;
    const playButton = article.querySelector(`#play-button-${index}`);
    if (playButton) {
        playButton.addEventListener("click", function (e) {
            e.preventDefault();
            window.location.href = downloadLink;
        });
        playButton.addEventListener('mouseenter', () => {
            const url = `/play_recording/${itemData.filename}`;
            if (url) prefetch(url);
        });
    }
    const downloadButton = article.querySelector(`#download-button-${index}`);
    if (downloadButton) {
        downloadButton.addEventListener("click", function (e) {
            e.preventDefault();
            const link = document.createElement("a");
            link.href = `/load_recording/${itemData.share_hash}`;
            link.setAttribute("download", "");
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        });
    }

    return article;
}

async function loadTrendingArchives() {
    try {
        const response = await fetch('/trending_archives');
        if (!response.ok) throw new Error('Failed to fetch trending archives');
        const trendingArchives = await response.json();
        const trandingDivContainer = document.getElementById('trending-container');
        if (!trendingArchives || trendingArchives.length === 0){
            trandingDivContainer.classList.add("hidden");
            return;
        } else {
            trandingDivContainer.classList.remove("hidden");
        }

        const container = document.getElementById('trending-archives-container');
        container.innerHTML = '';
        trendingArchives.forEach((archive, index) => {
            const archiveWithAnalytics = {
                ...archive,
                groupName: "Trending",  // Add groupName for the getArchiveBroadcastElement function
            };

            const article = getArchiveBroadcastElement(archiveWithAnalytics, index);
            container.appendChild(article);
            requestAnimationFrame(() => {
                article.classList.add('show');
            });
        });
    } catch (error) {
        console.error('Error loading trending archives:', error);
        const container = document.getElementById('trending-archives-container');
        if (container) {
            container.innerHTML = `
                <h6 class="absolute padding center middle medium-width center-align">
                    Error loading trending broadcasts.
                </h6>`;
        }
    }
}

async function loadArchiveData() {
    try {
      const response = await fetch('/get_archive_data');
      if (!response.ok) {
        throw new Error('Failed to fetch archive data');
      }
      const archiveData = await response.json();

      // Flatten
      allItems = [];
      Object.entries(archiveData).forEach(([groupName, items]) => {
        items.forEach(itemData => {
          allItems.push({ groupName, ...itemData });
        });
      });

      // Build page controls
      const totalPages = Math.ceil(allItems.length / itemsPerPage);
      buildPageButtons(totalPages);

      // Render the first page
      currentPage = 1;
      renderPage(currentPage);

    } catch (err) {
      console.error(err);
    }
    if (window.innerWidth <= 600) {
        closeAllDetails();
    }
}

function renderPage(pageNumber) {
    contentsContainer.innerHTML = "";
    const searchInput = document.getElementById('search');
    const query = searchInput.value.toLowerCase().replace(/ /g, '');

    const startIndex = (pageNumber - 1) * itemsPerPage;
    const endIndex = startIndex + itemsPerPage;
    let itemsToRender = [];

    if (query.length === 0) {
        itemsToRender = allItems.slice(startIndex, endIndex);
    } else {
        itemsToRender = allItems.filter(item => item.filename.replace('_', ':').replace('.mp3', '').toLowerCase().includes(query));
    }

    const fragment = document.createDocumentFragment();

    itemsToRender.forEach((itemData, index) => {
        const article = getArchiveBroadcastElement(itemData, startIndex + index);
        fragment.appendChild(article);
        requestAnimationFrame(() => {
            article.classList.add('show');
        });
    });

    contentsContainer.appendChild(fragment);

    // Update pagination controls
    updatePaginationButtons();
    searchAndFilter();
}

function buildPageButtons(totalPages) {
    pageNumbersContainer.innerHTML = "";
    for (let i = 1; i <= totalPages; i++) {
        const btn = document.createElement('button');
        btn.className = 'border chip circle small-round';
        btn.textContent = i;
        btn.addEventListener('click', () => {
            currentPage = i;
            renderPage(currentPage);
        });
        pageNumbersContainer.appendChild(btn);
    }
}

function updatePaginationButtons() {
    const totalPages = Math.ceil(allItems.length / itemsPerPage);

    if (currentPage <= 1) {
        prevPageBtn.disabled = true;
    } else {
        prevPageBtn.disabled = false;
    }

    if (currentPage >= totalPages) {
        nextPageBtn.disabled = true;
    } else {
        nextPageBtn.disabled = false;
    }

    Array.from(pageNumbersContainer.children).forEach(btn => {
        btn.classList.remove("primary");
        btn.disabled = false;
        if (parseInt(btn.textContent, 10) === currentPage) {
            btn.classList.add("primary");
            btn.disabled = true;
            btn.scrollIntoView({
                behavior: "smooth",
                block: "nearest",
                inline: "center"
            });
        }
    });
}

function goToPreviousPage() {
    if (currentPage > 1) {
        currentPage--;
        renderPage(currentPage);
    }
}

function goToNextPage() {
    const totalPages = Math.ceil(allItems.length / itemsPerPage);
    if (currentPage < totalPages) {
        currentPage++;
        renderPage(currentPage);
    }
}

async function updateEventCount() {
    const response = await fetch('/get_event_count');
    if (!response.ok) throw new Error('Failed to fetch event count');
    const data = await response.json();
    const broadcastCount = data.broadcast_count;
    const scheduledBroadcastCount = data.scheduled_broadcast_count;

    document.querySelectorAll("#event-tooltip-status").forEach(eventTooltipStatus => {
        let message = "";
        if (broadcastCount >= 1)
            message += `${broadcastCount} active broadcast${broadcastCount > 1 ? "s" : ""}<br>`;
        if (scheduledBroadcastCount >= 1)
            message += `${scheduledBroadcastCount} scheduled broadcast${scheduledBroadcastCount > 1 ? "s" : ""}`;
        if (broadcastCount + scheduledBroadcastCount === 0)
            message = "No broadcasts currently<br>online or events scheduled.";
        eventTooltipStatus.innerHTML = message;
    });

    document.querySelectorAll("#event-count").forEach(eventCount => {
        if (broadcastCount + scheduledBroadcastCount === 0) {
            eventCount.classList.add('hidden');
            return;
        }else{
            eventCount.classList.remove('hidden');
        }
        eventCount.textContent = broadcastCount + scheduledBroadcastCount;
    });
}

document.addEventListener('DOMContentLoaded', async function () {
    contentsContainer = document.getElementById('contents');
    prevPageBtn = document.getElementById('prev-page-btn');
    nextPageBtn = document.getElementById('next-page-btn');
    pageNumbersContainer = document.getElementById('page-numbers');

    // Hook up prev/next
    prevPageBtn.addEventListener('click', goToPreviousPage);
    nextPageBtn.addEventListener('click', goToNextPage);
    await Promise.all([
        loadArchiveData(),
        updateEventCount(),
        loadTrendingArchives()
    ]);

    setInterval(updateEventCount, 1000 * 60);
    setInterval(loadTrendingArchives, 5000 * 60);
});

document.addEventListener('DOMContentLoaded', function () {
    loadTheme();
    if (window.innerWidth <= 600) {
        closeAllDetails();
    }
    let lastWidth = window.innerWidth;
    const searchInput = document.getElementById('search');

    // document.getElementById('toggle-theme').addEventListener('click', toggleMode);

    searchInput.addEventListener('input', () => {
        renderPage(currentPage);
    });

    window.addEventListener('resize', () => {
        const currentWidth = window.innerWidth;
        if (currentWidth !== lastWidth) {
            lastWidth = currentWidth; // Update the last known width
        }
    });
});
