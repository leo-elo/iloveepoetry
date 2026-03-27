(function () {
  "use strict";

  var searchData = null;
  var debounceTimer = null;

  // Detect baseurl from the site's configuration
  function getBaseUrl() {
    var link = document.querySelector('link[rel="stylesheet"]');
    if (link) {
      var href = link.getAttribute('href');
      var match = href.match(/^(.*?)\/assets\//);
      if (match && match[1]) {
        return match[1];
      }
    }
    return "";
  }

  var baseUrl = getBaseUrl();

  // Load search data
  function loadSearchData() {
    if (searchData !== null) return;

    var url = baseUrl + "/search-data.json";
    var xhr = new XMLHttpRequest();
    xhr.open("GET", url, true);
    xhr.onreadystatechange = function () {
      if (xhr.readyState === 4 && xhr.status === 200) {
        try {
          searchData = JSON.parse(xhr.responseText);
        } catch (e) {
          searchData = [];
        }
      }
    };
    xhr.send();
  }

  // Score a post against the query
  function scorePost(post, query) {
    var q = query.toLowerCase();
    var score = 0;

    if (post.title && post.title.toLowerCase().indexOf(q) !== -1) {
      score += 10;
    }
    if (post.excerpt && post.excerpt.toLowerCase().indexOf(q) !== -1) {
      score += 5;
    }
    if (post.category && String(post.category).toLowerCase().indexOf(q) !== -1) {
      score += 3;
    }

    return score;
  }

  // Perform the search
  function performSearch(query) {
    var searchResults = document.getElementById("searchResults");
    if (!searchData || !query || query.trim().length < 2) {
      hideResults();
      return;
    }

    // Detect current language from URL
    var currentLang = window.location.pathname.indexOf('/es/') !== -1 ? 'es' : 'en';

    var results = [];
    for (var i = 0; i < searchData.length; i++) {
      var postLang = searchData[i].lang || 'en';
      if (postLang !== currentLang) continue;
      var s = scorePost(searchData[i], query);
      if (s > 0) {
        results.push({ post: searchData[i], score: s });
      }
    }

    // Sort by score descending
    results.sort(function (a, b) {
      return b.score - a.score;
    });

    // Top 10
    results = results.slice(0, 10);

    displayResults(results, query);
  }

  // Display results in the dropdown
  function displayResults(results, query) {
    var searchResults = document.getElementById("searchResults");
    if (!searchResults) return;

    if (results.length === 0) {
      searchResults.innerHTML =
        '<div class="search-no-results">No results found for "' +
        escapeHtml(query) +
        '"</div>';
      searchResults.classList.remove("hidden");
      return;
    }

    var html = "";
    for (var i = 0; i < results.length; i++) {
      var post = results[i].post;
      var postUrl = baseUrl + post.url;
      html += '<a class="search-result-item" href="' + escapeHtml(postUrl) + '">';
      html +=
        '<div class="search-result-title">' + escapeHtml(post.title) + "</div>";
      if (post.excerpt) {
        html +=
          '<div class="search-result-excerpt">' +
          escapeHtml(truncate(post.excerpt, 100)) +
          "</div>";
      }
      if (post.date || post.category) {
        html += '<div class="search-result-meta">';
        if (post.date) html += escapeHtml(post.date);
        if (post.date && post.category) html += " &middot; ";
        if (post.category) html += escapeHtml(post.category);
        html += "</div>";
      }
      html += "</a>";
    }

    searchResults.innerHTML = html;
    searchResults.classList.remove("hidden");
  }

  function hideResults() {
    var searchResults = document.getElementById("searchResults");
    if (searchResults) {
      searchResults.classList.add("hidden");
      searchResults.innerHTML = "";
    }
  }

  function escapeHtml(str) {
    if (!str) return "";
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function truncate(str, len) {
    if (!str) return "";
    if (str.length <= len) return str;
    return str.substring(0, len) + "...";
  }

  // Load search data eagerly
  loadSearchData();

  // Initialize search on DOMContentLoaded to ensure footer elements exist
  document.addEventListener("DOMContentLoaded", function () {
    var searchInput = document.getElementById("footerSearchInput");
    var searchResults = document.getElementById("searchResults");

    if (searchInput) {
      searchInput.addEventListener("focus", function () {
        loadSearchData();
      });

      searchInput.addEventListener("input", function () {
        var query = this.value;
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(function () {
          performSearch(query);
        }, 300);
      });
    }

    // Close results on outside click
    document.addEventListener("click", function (e) {
      if (
        searchResults &&
        searchInput &&
        !searchResults.contains(e.target) &&
        e.target !== searchInput
      ) {
        hideResults();
      }
    });

    // Mobile hamburger menu toggle
    var toggle = document.querySelector(".hamburger-toggle");
    var nav = document.getElementById("siteNav");

    if (toggle && nav) {
      toggle.addEventListener("click", function () {
        var isOpen = nav.classList.toggle("open");
        toggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
      });
    }
  });
})();
