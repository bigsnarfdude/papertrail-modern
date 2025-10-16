// PaperTrail Modern Dashboard JavaScript

const API_BASE_URL = '/api/v1';
let currentSystem = 'production_db';
let eventSource = null;
const MAX_EVENTS = 50;

// Initialize dashboard on load
document.addEventListener('DOMContentLoaded', function() {
    console.log('Initializing PaperTrail Modern Dashboard...');
    refreshDashboard();
    connectEventStream();

    // Auto-refresh every 30 seconds
    setInterval(refreshDashboard, 30000);
});

// Refresh all dashboard data
async function refreshDashboard() {
    console.log('Refreshing dashboard for system:', currentSystem);
    await Promise.all([
        loadMetricsSummary(),
        loadTopUsers(),
        loadTopIPs()
    ]);
}

// Load metrics summary
async function loadMetricsSummary() {
    try {
        const response = await fetch(`${API_BASE_URL}/compliance/summary/${currentSystem}`);

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();

        // Update metrics
        document.getElementById('unique-users-daily').textContent =
            formatNumber(data.daily.unique_users);
        document.getElementById('unique-users-hourly').textContent =
            formatNumber(data.hourly.unique_users);
        document.getElementById('unique-ips-daily').textContent =
            formatNumber(data.daily.unique_ips);
        document.getElementById('unique-sessions-hourly').textContent =
            formatNumber(data.hourly.unique_sessions);

    } catch (error) {
        console.error('Error loading metrics summary:', error);
        showError('Failed to load metrics');
    }
}

// Load top active users
async function loadTopUsers() {
    try {
        const response = await fetch(
            `${API_BASE_URL}/compliance/top/active_users?system=${currentSystem}&k=10&window=1h`
        );

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();

        const container = document.getElementById('top-users');

        if (data.items && data.items.length > 0) {
            container.innerHTML = data.items.map(item => `
                <div class="top-item">
                    <span class="top-item-name">${escapeHtml(item.item)}</span>
                    <span class="top-item-count">${formatNumber(item.count)}</span>
                </div>
            `).join('');
        } else {
            container.innerHTML = '<div class="loading">No data available</div>';
        }

    } catch (error) {
        console.error('Error loading top users:', error);
        document.getElementById('top-users').innerHTML =
            '<div class="loading">Error loading data</div>';
    }
}

// Load top active IPs
async function loadTopIPs() {
    try {
        const response = await fetch(
            `${API_BASE_URL}/compliance/top/active_ips?system=${currentSystem}&k=10&window=1h`
        );

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();

        const container = document.getElementById('top-ips');

        if (data.items && data.items.length > 0) {
            container.innerHTML = data.items.map(item => `
                <div class="top-item">
                    <span class="top-item-name">${escapeHtml(item.item)}</span>
                    <span class="top-item-count">${formatNumber(item.count)}</span>
                </div>
            `).join('');
        } else {
            container.innerHTML = '<div class="loading">No data available</div>';
        }

    } catch (error) {
        console.error('Error loading top IPs:', error);
        document.getElementById('top-ips').innerHTML =
            '<div class="loading">Error loading data</div>';
    }
}

// Check user activity (Bloom filter)
async function checkActivity() {
    const userId = document.getElementById('check-user-id').value.trim();
    const system = document.getElementById('check-system').value.trim();
    const window = document.getElementById('check-window').value;
    const resultDiv = document.getElementById('activity-result');

    if (!userId) {
        resultDiv.innerHTML = '<div class="result error">Please enter a user ID</div>';
        return;
    }

    if (!system) {
        resultDiv.innerHTML = '<div class="result error">Please enter a system name</div>';
        return;
    }

    try {
        const response = await fetch(
            `${API_BASE_URL}/compliance/activity/check?user_id=${encodeURIComponent(userId)}&system=${encodeURIComponent(system)}&window=${window}`
        );

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();

        const resultClass = data.accessed ? 'success' : 'error';
        const resultText = data.accessed
            ? `✓ User "${userId}" accessed "${system}" in the last ${window}`
            : `✗ User "${userId}" did NOT access "${system}" in the last ${window}`;

        resultDiv.innerHTML = `
            <div class="result ${resultClass}">
                ${resultText}
                <br>
                <small>Probability: ${(data.probability * 100).toFixed(1)}% (${data.note})</small>
            </div>
        `;

    } catch (error) {
        console.error('Error checking activity:', error);
        resultDiv.innerHTML = '<div class="result error">Error checking activity</div>';
    }
}

// Connect to SSE event stream
function connectEventStream() {
    if (eventSource) {
        eventSource.close();
    }

    console.log('Connecting to event stream...');
    eventSource = new EventSource(`${API_BASE_URL}/stream`);

    eventSource.onopen = function() {
        console.log('Event stream connected');
        updateConnectionStatus(true);
    };

    eventSource.onmessage = function(event) {
        try {
            const data = JSON.parse(event.data);
            addEventToStream(data);
        } catch (error) {
            console.error('Error parsing event:', error);
        }
    };

    eventSource.onerror = function(error) {
        console.error('Event stream error:', error);
        updateConnectionStatus(false);

        // Try to reconnect after 5 seconds
        setTimeout(() => {
            if (eventSource.readyState === EventSource.CLOSED) {
                console.log('Attempting to reconnect...');
                connectEventStream();
            }
        }, 5000);
    };
}

// Add event to stream display
function addEventToStream(event) {
    const streamContainer = document.getElementById('event-stream');

    // Remove "waiting" message if present
    const waitingMsg = streamContainer.querySelector('.event-item');
    if (waitingMsg && waitingMsg.textContent === 'Waiting for events...') {
        streamContainer.innerHTML = '';
    }

    // Create event element
    const eventEl = document.createElement('div');
    eventEl.className = 'event-item';

    const timestamp = event.timestamp ? new Date(event.timestamp).toLocaleTimeString() : 'now';

    eventEl.innerHTML = `
        <span class="event-type">${escapeHtml(event.event_type || event.type || 'event')}</span>
        ${event.system ? `@ ${escapeHtml(event.system)}` : ''}
        ${event.user_id ? `- User: ${escapeHtml(event.user_id)}` : ''}
        <span class="event-timestamp">${timestamp}</span>
    `;

    // Add to top of stream
    streamContainer.insertBefore(eventEl, streamContainer.firstChild);

    // Keep only last MAX_EVENTS
    while (streamContainer.children.length > MAX_EVENTS) {
        streamContainer.removeChild(streamContainer.lastChild);
    }
}

// Update connection status indicator
function updateConnectionStatus(connected) {
    const indicator = document.getElementById('connection-indicator');
    const text = document.getElementById('connection-text');

    if (connected) {
        indicator.className = 'indicator connected';
        text.textContent = 'Connected';
    } else {
        indicator.className = 'indicator disconnected';
        text.textContent = 'Disconnected';
    }
}

// Change active system
function changeSystem() {
    currentSystem = document.getElementById('system-select').value;
    console.log('System changed to:', currentSystem);
    refreshDashboard();
}

// Submit test event
async function submitTestEvent() {
    const testEvent = {
        event_type: 'user_login',
        user_id: 'test_user_' + Math.floor(Math.random() * 1000),
        system: currentSystem,
        timestamp: new Date().toISOString(),
        metadata: {
            ip: `192.168.1.${Math.floor(Math.random() * 255)}`,
            status: 'success',
            test: true
        }
    };

    try {
        const response = await fetch(`${API_BASE_URL}/events`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(testEvent)
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();
        console.log('Test event submitted:', data);

        // Refresh dashboard after a short delay
        setTimeout(refreshDashboard, 1000);

    } catch (error) {
        console.error('Error submitting test event:', error);
        showError('Failed to submit test event');
    }
}

// Utility functions
function formatNumber(num) {
    if (num === undefined || num === null) return '--';
    return num.toLocaleString();
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showError(message) {
    console.error(message);
    // Could show toast notification here
}

// Cleanup on page unload
window.addEventListener('beforeunload', function() {
    if (eventSource) {
        eventSource.close();
    }
});
