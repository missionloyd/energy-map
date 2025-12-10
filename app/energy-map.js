// energy-climate correlation map
// features: clustering, search, variable selection, tabbed popups

// configuration

var CLIMATE_VARIABLES = {
    temperature: { name: 'Temperature', unit: 'C', color: '#E74C3C' },
    humidity: { name: 'Humidity', unit: '%', color: '#3498DB' },
    pressure: { name: 'Pressure', unit: 'hPa', color: '#9B59B6' },
    cloud_cover: { name: 'Cloud Cover', unit: '%', color: '#95A5A6' },
    solar_radiation: { name: 'Solar Radiation', unit: 'W/m2', color: '#F39C12' },
    precipitation: { name: 'Precipitation', unit: 'mm', color: '#1ABC9C' },
    wind_speed: { name: 'Wind Speed', unit: 'm/s', color: '#2ECC71' },
    wind_direction: { name: 'Wind Direction', unit: 'deg', color: '#E67E22' }
};

var currentVariable = 'temperature';
var allRegionData = [];
var markers = {};
var clusterGroup = null;

// 66 balancing authority codes
var regionCodes = [
    'PJM', 'MISO', 'CISO', 'NYIS', 'ISNE', 'SWPP', 'ERCO',
    'BPAT', 'PACW', 'PACE', 'WACM', 'WALC', 'WAUW', 'NWMT', 'IPCO', 'AVA',
    'PSEI', 'SCL', 'TPWR', 'PGE', 'CHPD', 'DOPD', 'GCPD', 'BANC', 'TIDC',
    'LDWP', 'IID', 'AZPS', 'SRP', 'TEPC', 'EPE', 'PNM', 'NEVP', 'DEAA',
    'HGMA', 'PSCO', 'SPA', 'AECI', 'GWA', 'WWA', 'TVA', 'SOCO', 'DUK',
    'CPLE', 'CPLW', 'SC', 'SCEG', 'AEC', 'SEPA', 'FPL', 'FPC', 'TEC',
    'JEA', 'SEC', 'FMPP', 'GVL', 'TAL', 'HST', 'NSB', 'YAD', 'LGEE',
    'EEI', 'AVRN', 'GRIF', 'GRID', 'GLHB'
];

// map initialization

var map = L.map('energymap').setView([39.0, -98.0], 4);

// base layers
var streetMap = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 18
});

var satelliteMap = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
    attribution: 'Tiles &copy; Esri',
    maxZoom: 18
});

var darkMap = L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
    maxZoom: 19
});

darkMap.addTo(map);

// layer control
var baseMaps = {
    "Street Map": streetMap,
    "Satellite": satelliteMap,
    "Dark Mode": darkMap
};

L.control.layers(baseMaps).addTo(map);

// helper functions

function getCorrelationData(data, variable) {
    // get correlation for specific variable
    if (data.correlations && data.correlations[variable]) {
        return data.correlations[variable];
    }
    return null;
}

function getStrengthColor(r, strength) {
    if (strength === 'strong') {
        return r < 0 ? '#0072B2' : '#E69F00';
    } else if (strength === 'moderate') {
        return '#F0E442';
    } else {
        return '#999999';
    }
}

function getRadius(strength) {
    return strength === 'strong' ? 12 :
           strength === 'moderate' ? 9 : 6;
}

function formatVariableName(varKey) {
    return CLIMATE_VARIABLES[varKey] ? CLIMATE_VARIABLES[varKey].name : varKey;
}

function formatUnit(varKey) {
    return CLIMATE_VARIABLES[varKey] ? CLIMATE_VARIABLES[varKey].unit : '';
}

// popup creation

function createPopup(data) {
    var correlation = getCorrelationData(data, currentVariable);
    if (!correlation) {
        correlation = { r: 0, r2: 0, strength: 'weak', direction: 'positive', n: 0, mean: 0 };
    }

    var loadType = correlation.direction === 'negative' ?
        'Negative (colder/lower = more demand)' :
        'Positive (hotter/higher = more demand)';

    var varName = formatVariableName(currentVariable);
    var varUnit = formatUnit(currentVariable);

    // build correlations table for all variables
    var correlationsTable = '<table class="correlations-table">' +
        '<tr><th>Variable</th><th>r</th><th>R²</th><th>Strength</th></tr>';

    if (data.correlations) {
        for (var varKey in CLIMATE_VARIABLES) {
            if (data.correlations[varKey]) {
                var c = data.correlations[varKey];
                var isActive = varKey === currentVariable ? ' class="active"' : '';
                correlationsTable += '<tr' + isActive + '>' +
                    '<td>' + formatVariableName(varKey) + '</td>' +
                    '<td>' + c.r.toFixed(3) + '</td>' +
                    '<td>' + (c.r2 * 100).toFixed(1) + '%</td>' +
                    '<td><span class="strength-badge ' + c.strength + '">' + c.strength + '</span></td>' +
                    '</tr>';
            }
        }
    }
    correlationsTable += '</table>';

    // build popup html with tabs
    var html = '<div class="region-popup">' +
        '<div class="popup-header">' +
            '<h3>' + data.name + '</h3>' +
            '<span class="region-code">' + data.region + '</span>' +
        '</div>' +
        '<div class="popup-tabs">' +
            '<button class="tab active" data-tab="overview">Overview</button>' +
            '<button class="tab" data-tab="correlations">All Variables</button>' +
        '</div>' +
        '<div class="tab-content" id="tab-overview">' +
            '<p><strong>Current Variable:</strong> ' + varName + '</p>' +
            '<p><strong>Correlation (r):</strong> ' + correlation.r.toFixed(3) + '</p>' +
            '<p><strong>R² (variance explained):</strong> ' + (correlation.r2 * 100).toFixed(1) + '%</p>' +
            '<p><strong>Strength:</strong> <span class="strength-badge ' + correlation.strength + '">' + correlation.strength.toUpperCase() + '</span></p>' +
            '<p><strong>Direction:</strong> ' + loadType + '</p>' +
            '<hr>' +
            '<p><em>Sample: ' + (correlation.n || data.n_observations || 0).toLocaleString() + ' hourly observations</em></p>' +
            '<p><em>Avg Demand: ' + (data.energy_stats ? data.energy_stats.mean : data.energy_mean || 0).toLocaleString() + ' MW</em></p>' +
            '<p><em>Avg ' + varName + ': ' + (correlation.mean || 0).toFixed(1) + varUnit + '</em></p>' +
        '</div>' +
        '<div class="tab-content hidden" id="tab-correlations">' +
            correlationsTable +
        '</div>' +
    '</div>';

    return html;
}

function initPopupTabs(container) {
    var tabs = container.querySelectorAll('.tab');
    var contents = container.querySelectorAll('.tab-content');

    tabs.forEach(function(tab) {
        tab.addEventListener('click', function() {
            // remove active from all tabs and hide all content
            tabs.forEach(function(t) { t.classList.remove('active'); });
            contents.forEach(function(c) { c.classList.add('hidden'); });

            // activate clicked tab
            tab.classList.add('active');
            var tabId = 'tab-' + tab.getAttribute('data-tab');
            var content = container.querySelector('#' + tabId);
            if (content) {
                content.classList.remove('hidden');
            }
        });
    });
}

// marker management

function createMarker(data) {
    var correlation = getCorrelationData(data, currentVariable);
    if (!correlation) {
        correlation = { r: 0, strength: 'weak' };
    }

    var marker = L.circleMarker([data.lat, data.lng], {
        radius: getRadius(correlation.strength),
        fillColor: getStrengthColor(correlation.r, correlation.strength),
        color: '#000',
        weight: 1,
        opacity: 1,
        fillOpacity: 0.8
    });

    marker.bindPopup(createPopup(data), { maxWidth: 320, minWidth: 280 });

    // initialize tabs when popup opens
    marker.on('popupopen', function(e) {
        var container = e.popup.getElement();
        if (container) {
            initPopupTabs(container);
        }
    });

    marker.regionData = data;
    return marker;
}

function updateAllMarkers() {
    if (!clusterGroup) return;

    clusterGroup.clearLayers();

    allRegionData.forEach(function(data) {
        var marker = createMarker(data);
        markers[data.region] = marker;
        clusterGroup.addLayer(marker);
    });
}

// clustering

function initClusterGroup() {
    clusterGroup = L.markerClusterGroup({
        maxClusterRadius: 50,
        spiderfyOnMaxZoom: true,
        showCoverageOnHover: false,
        zoomToBoundsOnClick: true,
        iconCreateFunction: function(cluster) {
            var childMarkers = cluster.getAllChildMarkers();
            var totalR = 0;
            var count = 0;

            childMarkers.forEach(function(m) {
                if (m.regionData) {
                    var corr = getCorrelationData(m.regionData, currentVariable);
                    if (corr) {
                        totalR += Math.abs(corr.r);
                        count++;
                    }
                }
            });

            var avgR = count > 0 ? totalR / count : 0;
            var strength = avgR >= 0.5 ? 'strong' : avgR >= 0.3 ? 'moderate' : 'weak';
            var color = strength === 'strong' ? '#E69F00' : strength === 'moderate' ? '#F0E442' : '#999999';

            var size = Math.min(40 + count * 2, 60);

            return L.divIcon({
                html: '<div class="cluster-icon" style="background-color: ' + color + '; width: ' + size + 'px; height: ' + size + 'px; line-height: ' + size + 'px;">' + count + '</div>',
                className: 'marker-cluster-custom',
                iconSize: L.point(size, size)
            });
        }
    });

    map.addLayer(clusterGroup);
}

// search bar

function initSearchControl() {
    var searchControl = L.control({ position: 'topleft' });

    searchControl.onAdd = function() {
        var div = L.DomUtil.create('div', 'search-control');
        div.innerHTML = '<div class="search-wrapper">' +
            '<input type="text" id="region-search" placeholder="Search regions..." autocomplete="off">' +
            '<div id="search-results" class="search-results hidden"></div>' +
            '</div>';

        L.DomEvent.disableClickPropagation(div);
        L.DomEvent.disableScrollPropagation(div);

        return div;
    };

    searchControl.addTo(map);

    // initialize search functionality after dom is ready
    setTimeout(function() {
        var searchInput = document.getElementById('region-search');
        var resultsContainer = document.getElementById('search-results');

        if (!searchInput || !resultsContainer) return;

        searchInput.addEventListener('input', function(e) {
            var query = e.target.value.toLowerCase();
            if (query.length < 2) {
                resultsContainer.classList.add('hidden');
                return;
            }

            var matches = allRegionData.filter(function(r) {
                return r.name.toLowerCase().includes(query) ||
                       r.region.toLowerCase().includes(query);
            }).slice(0, 8);

            if (matches.length === 0) {
                resultsContainer.innerHTML = '<div class="no-results">No regions found</div>';
            } else {
                resultsContainer.innerHTML = matches.map(function(r) {
                    return '<div class="search-result" data-region="' + r.region + '">' +
                        '<strong>' + r.region + '</strong> - ' + r.name +
                        '</div>';
                }).join('');
            }

            resultsContainer.classList.remove('hidden');

            // bind click events
            resultsContainer.querySelectorAll('.search-result').forEach(function(el) {
                el.addEventListener('click', function() {
                    var regionCode = el.getAttribute('data-region');
                    zoomToRegion(regionCode);
                    resultsContainer.classList.add('hidden');
                    searchInput.value = '';
                });
            });
        });

        searchInput.addEventListener('focus', function() {
            if (searchInput.value.length >= 2) {
                resultsContainer.classList.remove('hidden');
            }
        });

        document.addEventListener('click', function(e) {
            if (!e.target.closest('.search-wrapper')) {
                resultsContainer.classList.add('hidden');
            }
        });
    }, 200);
}

function zoomToRegion(regionCode) {
    var region = allRegionData.find(function(r) { return r.region === regionCode; });
    if (region) {
        map.setView([region.lat, region.lng], 8);
        if (markers[regionCode]) {
            markers[regionCode].openPopup();
        }
    }
}

// variable selector

function initVariableSelector() {
    var selectorControl = L.control({ position: 'topright' });

    selectorControl.onAdd = function() {
        var div = L.DomUtil.create('div', 'variable-selector');
        var options = '';
        for (var varKey in CLIMATE_VARIABLES) {
            var selected = varKey === currentVariable ? ' selected' : '';
            options += '<option value="' + varKey + '"' + selected + '>' +
                CLIMATE_VARIABLES[varKey].name + '</option>';
        }

        div.innerHTML = '<h4>Climate Variable</h4>' +
            '<select id="variable-select">' + options + '</select>';

        L.DomEvent.disableClickPropagation(div);

        return div;
    };

    selectorControl.addTo(map);

    setTimeout(function() {
        var select = document.getElementById('variable-select');
        if (select) {
            select.addEventListener('change', function(e) {
                currentVariable = e.target.value;
                updateAllMarkers();
                updateLegend();
            });
        }
    }, 100);
}

// strength filter

function initStrengthFilter() {
    var filterControl = L.control({ position: 'topright' });

    filterControl.onAdd = function() {
        var div = L.DomUtil.create('div', 'strength-filter');
        div.innerHTML = '<h4>Filter by Strength</h4>' +
            '<label><input type="checkbox" id="filter-strong" checked> Strong</label><br>' +
            '<label><input type="checkbox" id="filter-moderate" checked> Moderate</label><br>' +
            '<label><input type="checkbox" id="filter-weak" checked> Weak</label>';

        L.DomEvent.disableClickPropagation(div);

        return div;
    };

    filterControl.addTo(map);

    setTimeout(function() {
        var filterStrong = document.getElementById('filter-strong');
        var filterModerate = document.getElementById('filter-moderate');
        var filterWeak = document.getElementById('filter-weak');

        function applyFilter() {
            var showStrong = filterStrong.checked;
            var showModerate = filterModerate.checked;
            var showWeak = filterWeak.checked;

            clusterGroup.clearLayers();

            allRegionData.forEach(function(data) {
                var corr = getCorrelationData(data, currentVariable);
                if (!corr) return;

                var show = (corr.strength === 'strong' && showStrong) ||
                          (corr.strength === 'moderate' && showModerate) ||
                          (corr.strength === 'weak' && showWeak);

                if (show && markers[data.region]) {
                    clusterGroup.addLayer(markers[data.region]);
                }
            });
        }

        if (filterStrong) filterStrong.addEventListener('change', applyFilter);
        if (filterModerate) filterModerate.addEventListener('change', applyFilter);
        if (filterWeak) filterWeak.addEventListener('change', applyFilter);
    }, 100);
}

// legend

var legend;

function initLegend() {
    legend = L.control({ position: 'bottomright' });

    legend.onAdd = function() {
        var div = L.DomUtil.create('div', 'legend');
        updateLegendContent(div);
        return div;
    };

    legend.addTo(map);
}

function updateLegend() {
    var div = document.querySelector('.legend');
    if (div) {
        updateLegendContent(div);
    }
}

function updateLegendContent(div) {
    var varName = formatVariableName(currentVariable);
    div.innerHTML = '<h4>' + varName + '-Demand Correlation (2020 - Present)</h4>' +
        '<i style="background:#0072B2"></i> Strong Negative (r &lt; -0.5)<br>' +
        '<i style="background:#E69F00"></i> Strong Positive (r &gt; 0.5)<br>' +
        '<i style="background:#F0E442"></i> Moderate (0.3 &lt;= |r| &lt; 0.5)<br>' +
        '<i style="background:#999999"></i> Weak (|r| &lt; 0.3)<br>';
}

// data loading

function loadAllData() {
    var loadedCount = 0;

    regionCodes.forEach(function(code) {
        $.getJSON('data/clean_data/' + code + '.json', function(data) {
            allRegionData.push(data);
            var marker = createMarker(data);
            markers[code] = marker;
            clusterGroup.addLayer(marker);

            loadedCount++;
            if (loadedCount === regionCodes.length) {
                console.log('Loaded ' + loadedCount + ' regions');
            }
        }).fail(function() {
            console.log('Failed to load: ' + code);
            loadedCount++;
        });
    });
}

// initialization

initClusterGroup();
initSearchControl();
initVariableSelector();
initStrengthFilter();
initLegend();
loadAllData();
