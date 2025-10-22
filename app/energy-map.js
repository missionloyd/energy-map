// init map
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

// default layer
darkMap.addTo(map);

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

// layer group for correlation markers
var correlationLayer = L.layerGroup();

// helper function for displaying colors and size
function getStrengthColor(r, strength) {
    // strong correlations: Blue (heating) or Orange (cooling)
    if (strength === 'strong') {
        return r < 0 ? '#0072B2' : '#E69F00';
    // moderate: Yellow
    } else if (strength === 'moderate') {
        return '#F0E442';
    // wmeak: Gray
    } else {
        return '#999999';
    }
}

function getRadius(strength) {
    return strength === 'strong' ? 12 :
           strength === 'moderate' ? 9 : 6;
}

function createPopup(data) {
    var loadType = data.direction === 'negative' ?
        'Heating Load (colder → more demand)' :
        'Cooling Load (hotter → more demand)';

    return '<h3>' + data.name + '</h3>' +
           '<p><strong>Region Code:</strong> ' + data.region + '</p>' +
           '<hr>' +
           '<p><strong>Correlation (r):</strong> ' + data.r.toFixed(3) + '</p>' +
           '<p><strong>R² (variance explained):</strong> ' + (data.r2 * 100).toFixed(1) + '%</p>' +
           '<p><strong>Strength:</strong> ' + data.strength.toUpperCase() + '</p>' +
           '<p><strong>Load Type:</strong> ' + loadType + '</p>' +
           '<hr>' +
           '<p><em>Sample: ' + data.n_observations.toLocaleString() + ' hourly observations</em></p>' +
           '<p><em>Avg Demand: ' + data.energy_mean.toLocaleString() + ' MW</em></p>' +
           '<p><em>Avg Temperature: ' + data.temp_mean.toFixed(1) + '°C</em></p>';
}

// correlation data for all regions
var loadedCount = 0;
var totalRegions = regionCodes.length;

regionCodes.forEach(function(code) {
    $.getJSON('clean_data/' + code + '.json', function(data) {
        // Create circle marker
        var marker = L.circleMarker([data.lat, data.lng], {
            radius: getRadius(data.strength),
            fillColor: getStrengthColor(data.r, data.strength),
            color: '#000',
            weight: 1,
            opacity: 1,
            fillOpacity: 0.8
        });

        marker.bindPopup(createPopup(data));
        correlationLayer.addLayer(marker);

        loadedCount++;
        if (loadedCount === totalRegions) {
            console.log('Loaded ' + loadedCount + ' regions');
        }
    }).fail(function() {
        console.log('Failed to load: ' + code);
        loadedCount++;
    });
});

correlationLayer.addTo(map);

// base maps and overlays
var baseMaps = {
    "Street Map": streetMap,
    "Satellite": satelliteMap,
    "Dark Mode": darkMap
};

var overlayMaps = {
    "Correlation Analysis": correlationLayer
};

L.control.layers(baseMaps, overlayMaps).addTo(map);

// legend
var legend = L.control({position: 'bottomright'});

legend.onAdd = function(map) {
    var div = L.DomUtil.create('div', 'legend');
    div.innerHTML = '<h4>Temperature-Demand Correlation (2024)</h4>' +
                    '<i style="background:#0072B2"></i> Strong Heating (r &lt; -0.5)<br>' +
                    '<i style="background:#E69F00"></i> Strong Cooling (r &gt; 0.5)<br>' +
                    '<i style="background:#F0E442"></i> Moderate (0.3 ≤ |r| &lt; 0.5)<br>' +
                    '<i style="background:#999999"></i> Weak (|r| &lt; 0.3)<br>';
    return div;
};

legend.addTo(map);
