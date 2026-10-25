import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Map, { Layer, Marker, NavigationControl, Source } from 'react-map-gl/maplibre';

const API = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000';
const EMPTY_FC = { type: 'FeatureCollection', features: [] };
const MAP_STYLE = 'https://tiles.openfreemap.org/styles/dark';
const INITIAL_START = { label: 'Melville Library', lat: 40.9146, lng: -73.1232 };
const INITIAL_END = { label: 'Stony Brook Union', lat: 40.9135, lng: -73.1177 };

const lightColor = [
  'case',
  ['<', ['get', 'light_score'], 0.3], '#657082',
  ['<', ['get', 'light_score'], 0.6], '#F2A65A',
  '#FFD85A',
];

function formatTime(seconds = 0) {
  const minutes = Math.max(1, Math.round(seconds / 60));
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return remainder ? `${hours} hr ${remainder} min` : `${hours} hr`;
}

function formatDistance(meters = 0) {
  return meters >= 1000 ? `${(meters / 1000).toFixed(1)} km` : `${Math.round(meters)} m`;
}

function percent(value = 0) {
  return `${Math.round(value * 100)}%`;
}

function coordinateText(point) {
  return `${point.lat.toFixed(5)}, ${point.lng.toFixed(5)}`;
}

function Stat({ label, value, sub }) {
  return <div className="stat"><span>{label}</span><strong>{value}</strong>{sub && <small>{sub}</small>}</div>;
}

function RouteOption({ type, route, active, onClick, deltaText }) {
  if (!route) return null;
  const bright = type === 'brightest';
  return (
    <button className={`route-option ${active ? 'route-option-active' : ''}`} onClick={onClick} type="button">
      <span className={`route-icon ${bright ? 'route-icon-bright' : ''}`}>{bright ? '✳' : '↗'}</span>
      <span className="route-option-main">
        <span className="route-option-title">{bright ? 'Brighter route' : 'Fastest route'} {active && <i>SELECTED</i>}</span>
        <span className="route-option-sub">{formatDistance(route.distance_m)} · {percent(route.pct_well_lit)} of path well lit*</span>
        {deltaText && <span className="route-delta">{deltaText}</span>}
      </span>
      <strong className="route-time">{formatTime(route.duration_s)}</strong>
    </button>
  );
}

export default function App() {
  const mapRef = useRef(null);
  const [start, setStart] = useState(INITIAL_START);
  const [destination, setDestination] = useState(INITIAL_END);
  const [startText, setStartText] = useState(INITIAL_START.label);
  const [destinationText, setDestinationText] = useState(INITIAL_END.label);
  const [alpha, setAlpha] = useState(2.3);
  const [selectedRoute, setSelectedRoute] = useState('brightest');
  const [pickMode, setPickMode] = useState(null);
  const [routeData, setRouteData] = useState(null);
  const [coverageData, setCoverageData] = useState(EMPTY_FC);
  const [lampsData, setLampsData] = useState(EMPTY_FC);
  const [selectedSegment, setSelectedSegment] = useState(null);
  const [showLamps, setShowLamps] = useState(false);
  const [showCoverage, setShowCoverage] = useState(false);
  const [showInfo, setShowInfo] = useState(false);
  const [loading, setLoading] = useState(false);
  const [searching, setSearching] = useState(null);
  const [error, setError] = useState('');
  const [apiStatus, setApiStatus] = useState('checking');
  const [demoMode, setDemoMode] = useState(true);
  const [usesMapillary, setUsesMapillary] = useState(false);
  const [toast, setToast] = useState('');

  const fastest = routeData?.fastest;
  const brightest = routeData?.brightest;
  const currentRoute = selectedRoute === 'brightest' ? brightest : fastest;
  const deltaMinutes = routeData ? Math.max(0, Math.round((routeData.delta?.extra_time_s || 0) / 60)) : 0;
  const deltaText = routeData && (routeData.delta.extra_time_s > 0 || routeData.delta.extra_distance_m > 0)
    ? `+${deltaMinutes} min · +${formatDistance(routeData.delta.extra_distance_m)}` : '';

  useEffect(() => {
    let cancelled = false;
    fetch(`${API}/api/health`)
      .then((r) => r.json())
      .then((data) => {
        if (cancelled) return;
        setApiStatus('online');
        setDemoMode(Boolean(data.demo_mode));
        setUsesMapillary(Boolean(data.uses_mapillary));
      })
      .catch(() => { if (!cancelled) setApiStatus('offline'); });
    fetch(`${API}/api/edges`).then((r) => r.json()).then((data) => { if (!cancelled) setCoverageData(data); }).catch(() => {});
    fetch(`${API}/api/lamps`).then((r) => r.json()).then((data) => { if (!cancelled) setLampsData(data); }).catch(() => {});
    return () => { cancelled = true; };
  }, []);

  const requestRoute = useCallback(async (origin = start, target = destination, weight = alpha) => {
    setLoading(true);
    setError('');
    setSelectedSegment(null);
    try {
      const params = new URLSearchParams({
        from_lat: origin.lat, from_lng: origin.lng,
        to_lat: target.lat, to_lng: target.lng,
        alpha: weight, pace: 1.4,
      });
      const response = await fetch(`${API}/api/route?${params.toString()}`);
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || 'Could not calculate these routes.');
      setRouteData(body);
      setDemoMode(Boolean(body.demo_mode));
      setUsesMapillary(Boolean(body.uses_mapillary));
      setSelectedRoute('brightest');
      setToast('Routes updated');
      window.setTimeout(() => setToast(''), 2200);
    } catch (err) {
      setError(err.message || 'The route service is unavailable.');
    } finally {
      setLoading(false);
    }
  }, [start, destination, alpha]);

  useEffect(() => {
    requestRoute(INITIAL_START, INITIAL_END, alpha);
    // Initial route only; interactive route updates happen on button click.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const choosePreset = (which, preset) => {
    if (which === 'start') {
      setStart(preset); setStartText(preset.label);
    } else {
      setDestination(preset); setDestinationText(preset.label);
    }
    setError('');
  };

  const resolveLocation = async (which) => {
    const query = which === 'start' ? startText.trim() : destinationText.trim();
    if (!query) return;
    setSearching(which); setError('');
    const coordinateMatch = query.match(/^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$/);
    try {
      let point;
      if (coordinateMatch) {
        point = { lat: Number(coordinateMatch[1]), lng: Number(coordinateMatch[2]), label: query };
      } else {
        const response = await fetch(`${API}/api/geocode?q=${encodeURIComponent(query)}`);
        const body = await response.json();
        if (!response.ok) throw new Error(body.detail || 'Could not find that place.');
        if (!body.results?.length) throw new Error('No results. Try a campus preset or click the map.');
        point = { lat: Number(body.results[0].lat), lng: Number(body.results[0].lon), label: body.results[0].label };
      }
      if (!Number.isFinite(point.lat) || !Number.isFinite(point.lng) || Math.abs(point.lat) > 90 || Math.abs(point.lng) > 180) {
        throw new Error('Enter coordinates as latitude, longitude.');
      }
      if (which === 'start') setStart(point); else setDestination(point);
      mapRef.current?.flyTo({ center: [point.lng, point.lat], zoom: 15, duration: 700 });
    } catch (err) {
      setError(err.message || 'Search failed.');
    } finally {
      setSearching(null);
    }
  };

  const onMapClick = (event) => {
    if (pickMode) {
      const point = {
        lng: event.lngLat.lng,
        lat: event.lngLat.lat,
        label: `${event.lngLat.lat.toFixed(5)}, ${event.lngLat.lng.toFixed(5)}`,
      };
      if (pickMode === 'start') { setStart(point); setStartText(point.label); }
      else { setDestination(point); setDestinationText(point.label); }
      setPickMode(null);
      setError('');
      return;
    }
    const feature = event.features?.[0];
    if (feature?.properties?.light_score !== undefined) setSelectedSegment(feature.properties);
  };

  const fitRoute = () => {
    const points = [start, destination].filter(Boolean);
    const minLng = Math.min(...points.map((p) => p.lng)) - 0.003;
    const maxLng = Math.max(...points.map((p) => p.lng)) + 0.003;
    const minLat = Math.min(...points.map((p) => p.lat)) - 0.002;
    const maxLat = Math.max(...points.map((p) => p.lat)) + 0.002;
    mapRef.current?.fitBounds([[minLng, minLat], [maxLng, maxLat]], { padding: 80, duration: 800 });
  };

  const coverageLayers = useMemo(() => ({
    id: 'coverage-lines', type: 'line',
    paint: { 'line-color': lightColor, 'line-width': 3, 'line-opacity': 0.72 },
    layout: { 'line-cap': 'round', 'line-join': 'round' },
  }), []);
  const routeLayers = useMemo(() => ({
    fastestCasing: { id: 'fastest-casing', type: 'line', paint: { 'line-color': '#080B12', 'line-width': 9, 'line-opacity': 0.82 }, layout: { 'line-cap': 'round', 'line-join': 'round' } },
    fastest: { id: 'fastest-line', type: 'line', paint: { 'line-color': lightColor, 'line-width': 5, 'line-opacity': selectedRoute === 'fastest' ? 0.98 : 0.40 }, layout: { 'line-cap': 'round', 'line-join': 'round' } },
    brightestCasing: { id: 'brightest-casing', type: 'line', paint: { 'line-color': '#080B12', 'line-width': 10, 'line-opacity': 0.95 }, layout: { 'line-cap': 'round', 'line-join': 'round' } },
    brightest: { id: 'brightest-line', type: 'line', paint: { 'line-color': lightColor, 'line-width': selectedRoute === 'brightest' ? 7 : 4, 'line-opacity': selectedRoute === 'brightest' ? 1 : 0.30 }, layout: { 'line-cap': 'round', 'line-join': 'round' } },
  }), [selectedRoute]);

  return (
    <main className="app-shell">
      <Map
        ref={mapRef}
        initialViewState={{ longitude: -73.1227, latitude: 40.9144, zoom: 14.1, pitch: 18 }}
        mapStyle={MAP_STYLE}
        onClick={onMapClick}
        interactiveLayerIds={['coverage-lines', ...(fastest ? ['fastest-line'] : []), ...(brightest ? ['brightest-line'] : [])]}
        cursor={pickMode ? 'crosshair' : undefined}
        attributionControl={false}
        reuseMaps
      >
        <NavigationControl position="bottom-right" showCompass={false} />
        <Source id="coverage-data" type="geojson" data={coverageData || EMPTY_FC}><Layer {...coverageLayers} layout={{ ...coverageLayers.layout, visibility: showCoverage ? 'visible' : 'none' }} /></Source>
        {fastest?.geometry && <Source id="fastest-data" type="geojson" data={fastest.geometry}>
          <Layer {...routeLayers.fastestCasing} /><Layer {...routeLayers.fastest} />
        </Source>}
        {brightest?.geometry && <Source id="brightest-data" type="geojson" data={brightest.geometry}>
          <Layer {...routeLayers.brightestCasing} /><Layer {...routeLayers.brightest} />
        </Source>}
        {showLamps && lampsData?.features?.length > 0 && <Source id="lamp-data" type="geojson" data={lampsData}>
          <Layer id="lamp-halo" type="circle" paint={{ 'circle-radius': 8, 'circle-color': '#FFD85A', 'circle-opacity': 0.18, 'circle-blur': 0.7 }} />
          <Layer id="lamp-core" type="circle" paint={{ 'circle-radius': 2.5, 'circle-color': '#FFE58A', 'circle-stroke-color': '#FFF5CF', 'circle-stroke-width': 0.5 }} />
        </Source>}
        <Marker longitude={start.lng} latitude={start.lat} anchor="center">
          <div className="map-pin map-pin-start"><span></span></div>
        </Marker>
        <Marker longitude={destination.lng} latitude={destination.lat} anchor="center">
          <div className="map-pin map-pin-end"><span>✦</span></div>
        </Marker>
      </Map>

      <header className="topbar">
        <div className="brand-mark"><span className="brand-spark">✳</span></div>
        <div className="brand-text"><strong>LUMEN <span>ROUTES</span></strong><small>WALK BY LIGHT</small></div>
        <div className="topbar-right">
          <div className={`api-pill ${apiStatus}`}><span></span>{apiStatus === 'online' ? 'ROUTING ONLINE' : apiStatus === 'offline' ? 'API OFFLINE' : 'CONNECTING'}</div>
          <button className="icon-button info-button" onClick={() => setShowInfo(true)} aria-label="About lighting data">i</button>
        </div>
      </header>

      <aside className="route-panel">
        <div className="panel-kicker"><span className="live-dot"></span> LIGHT-AWARE WALKING</div>
        <h1>Take the <em>brighter</em> way.</h1>
        <p className="panel-intro">Compare the quickest walk with a route that favors streets with more lighting evidence.</p>

        <div className="location-stack">
          <div className="location-symbols"><span className="origin-symbol"></span><span className="location-connector"></span><span className="destination-symbol">✦</span></div>
          <div className="location-fields">
            <div className="location-field">
              <label htmlFor="start-place">STARTING POINT</label>
              <div className="input-row"><input id="start-place" value={startText} onChange={(e) => setStartText(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && resolveLocation('start')} /><button className="pick-button" onClick={() => setPickMode('start')} title="Pick the start on the map">PICK</button><button className="search-button" onClick={() => resolveLocation('start')} disabled={searching === 'start'} aria-label="Search start">↵</button></div>
            </div>
            <div className="field-divider"></div>
            <div className="location-field">
              <label htmlFor="end-place">DESTINATION</label>
              <div className="input-row"><input id="end-place" value={destinationText} onChange={(e) => setDestinationText(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && resolveLocation('destination')} /><button className="pick-button" onClick={() => setPickMode('destination')} title="Pick the destination on the map">PICK</button><button className="search-button" onClick={() => resolveLocation('destination')} disabled={searching === 'destination'} aria-label="Search destination">↵</button></div>
            </div>
          </div>
        </div>
        <div className="preset-row">
          <span>TRY A CAMPUS ROUTE</span>
          <button onClick={() => { choosePreset('start', INITIAL_START); choosePreset('destination', INITIAL_END); requestRoute(INITIAL_START, INITIAL_END, alpha); }}>Library → Union</button>
          <button onClick={() => { const a = { label: 'Staller Center', lat: 40.9149, lng: -73.1201 }; const b = { label: 'Sports Complex', lat: 40.9121, lng: -73.1166 }; choosePreset('start', a); choosePreset('destination', b); requestRoute(a, b, alpha); }}>Staller → Sports</button>
        </div>

        <div className="section-rule"></div>
        <div className="slider-heading"><div><span className="eyebrow">ROUTE PREFERENCE</span><h2>Brightness <span>vs.</span> speed</h2></div><div className="slider-value">{Math.round(alpha / 3 * 100)}<small>%</small></div></div>
        <input className="preference-slider" type="range" min="0" max="3" step="0.1" value={alpha} onChange={(e) => setAlpha(Number(e.target.value))} style={{ '--slider-progress': `${alpha / 3 * 100}%` }} aria-label="Brightness versus speed" />
        <div className="slider-labels"><span>FASTEST</span><span>MORE LIGHTING</span></div>
        <button className="primary-button" onClick={() => requestRoute(start, destination, alpha)} disabled={loading || apiStatus === 'offline'}>
          {loading ? <><span className="spinner"></span> FINDING ROUTES…</> : <>FIND MY ROUTES <span>↗</span></>}
        </button>
        {pickMode && <div className="pick-banner">Click the map to set your {pickMode === 'start' ? 'starting point' : 'destination'}. <button onClick={() => setPickMode(null)}>Cancel</button></div>}
        {error && <div className="error-message">{error}</div>}

        {routeData && <>
          <div className="results-heading"><div><span className="eyebrow">YOUR OPTIONS</span><h2>Two ways to get there</h2></div><span className="route-count">02 ROUTES</span></div>
          <div className="route-options">
            <RouteOption type="fastest" route={fastest} active={selectedRoute === 'fastest'} onClick={() => setSelectedRoute('fastest')} />
            <RouteOption type="brightest" route={brightest} active={selectedRoute === 'brightest'} onClick={() => setSelectedRoute('brightest')} deltaText={deltaText} />
          </div>
          {selectedRoute === 'brightest' && brightest && <div className="tradeoff-note"><span className="tradeoff-icon">↗</span><span><strong>{deltaText || 'Similar travel time'}</strong> for {percent(brightest.pct_well_lit)} of the route with higher lighting evidence.</span></div>}
          <div className="detail-grid">
            <Stat label="LONGEST DIM STRETCH" value={formatDistance(currentRoute?.longest_dark_m || 0)} sub="continuous segment" />
            <Stat label="FIXTURES NEAR ROUTE" value={currentRoute?.lamp_count ?? '—'} sub="estimated count" />
          </div>
          <div className="confidence-note"><span className="confidence-icon">◌</span> {percent(currentRoute?.pct_low_confidence || 0)} of this route has low-confidence data.</div>
        </>}
        <div className="panel-footer"><span className="legend-dot legend-dim"></span><span className="legend-dot legend-mid"></span><span className="legend-dot legend-lit"></span><span>Less evidence</span><span className="legend-spacer"></span><span>More evidence</span></div>
      </aside>

      <div className="map-tools">
        <div className="map-tool-title">MAP LAYERS</div>
        <button className={`layer-toggle ${showLamps ? 'layer-active' : ''}`} onClick={() => setShowLamps((v) => !v)}><span className="layer-symbol lamp-symbol">✳</span><span>Light markers</span><span className="toggle-knob"></span></button>
        <button className={`layer-toggle ${showCoverage ? 'layer-active' : ''}`} onClick={() => setShowCoverage((v) => !v)}><span className="layer-symbol coverage-symbol">▱</span><span>Lighting coverage</span><span className="toggle-knob"></span></button>
        <button className="fit-button" onClick={fitRoute}>⌖ <span>FIT ROUTE</span></button>
      </div>

      {selectedSegment && <div className="segment-card">
        <button className="segment-close" onClick={() => setSelectedSegment(null)} aria-label="Close segment details">×</button>
        <span className="eyebrow">STREET SEGMENT</span>
        <div className="segment-score-row"><strong>{Math.round(Number(selectedSegment.light_score || 0) * 100)}<small>/100</small></strong><span className={`score-tag ${selectedSegment.light_score >= 0.6 ? 'score-lit' : selectedSegment.light_score >= 0.3 ? 'score-mid' : 'score-dim'}`}>{selectedSegment.light_score >= 0.6 ? 'MORE EVIDENCE' : selectedSegment.light_score >= 0.3 ? 'MIXED EVIDENCE' : 'LOW EVIDENCE'}</span></div>
        <div className="segment-stats"><div><span>Fixtures nearby</span><b>{selectedSegment.lamp_count ?? 0}</b></div><div><span>Longest gap</span><b>{formatDistance(selectedSegment.max_gap_m || 0)}</b></div><div><span>Data confidence</span><b>{percent(selectedSegment.confidence || 0)}</b></div></div>
        <small className="segment-source">Sources: {(selectedSegment.data_sources || ['unknown']).join(', ')}</small>
      </div>}

      <div className="map-caption"><span className="map-caption-dot"></span><span>STONY BROOK · CAMPUS DEMO</span><span className="caption-divider">/</span><span>{demoMode ? 'ILLUSTRATIVE DATA' : 'LOCAL LIGHTING GRAPH'}</span></div>
      <div className="map-attribution">© OpenStreetMap contributors · Basemap: OpenFreeMap{usesMapillary ? ' · Imagery/data © Mapillary' : ''}</div>
      {toast && <div className="toast-message">✓ {toast}</div>}
      {showInfo && <div className="modal-backdrop" onClick={() => setShowInfo(false)}><section className="info-modal" onClick={(e) => e.stopPropagation()}><button className="modal-close" onClick={() => setShowInfo(false)}>×</button><div className="modal-brand">✳ LUMEN ROUTES</div><h2>Lighting is one clue, not a guarantee.</h2><p>Lumen Routes compares walking paths using street-lighting evidence. A higher score means more lighting evidence was recorded or estimated for that segment. It does not measure actual brightness, prove that a lamp works, or guarantee that a route is safe.</p><div className="info-cards"><div><span className="info-swatch swatch-lit"></span><strong>More evidence</strong><small>More fixture or lighting signals</small></div><div><span className="info-swatch swatch-mid"></span><strong>Mixed evidence</strong><small>Some signals, with gaps</small></div><div><span className="info-swatch swatch-dim"></span><strong>Low evidence</strong><small>May be dim, incomplete, or outdated</small></div></div>{demoMode && <div className="demo-alert">DEMO MODE: route network, fixture markers, and scores are illustrative sample data—not observations of actual campus lighting.</div>}<p className="modal-footnote">Coverage can be incomplete or outdated. Daytime imagery shows fixtures, not necessarily nighttime illumination. Missing data is not proof that a street is dark.</p><button className="primary-button modal-done" onClick={() => setShowInfo(false)}>GOT IT</button></section></div>}
    </main>
  );
}
