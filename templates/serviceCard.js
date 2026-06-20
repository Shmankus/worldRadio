class ServiceCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
  }
  
  connectedCallback() {
    const service = this.getAttribute('service') || 'None';
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
        }
        .card {
          font-family: sans-serif;
          background: #f4f4f4;
          width: 250px;
          padding: 15px;
          border-radius: 8px;
          border-left: 5px solid #0076ff;
          box-sizing: border-box;
        }
        h3 { margin: 0 0 5px 0; color: #333; }
        p { margin: 0; color: #666; font-size: 14px; }
      </style>
      <div class="card">
        <h3>${service}</h3>
        <p id="status">Loading...</p>

<button id="stopButton" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2 px-4 rounded transition text-sm">
 Stop
 </button>


<button id="startButton" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2 px-4 rounded transition text-sm">
 Start
 </button>
      </div>
    `;
    
    // Fetch and update status after render
    this.checkServiceStatus(service);



    this.shadowRoot.getElementById("stopButton").addEventListener('click', () => {

      this.stopService(service);
      });
    
    this.shadowRoot.getElementById("startButton").addEventListener('click', () => {

      this.startService(service);
      });

  }
  
  async checkServiceStatus(serviceName) {
    try {
      const response = await fetch("http://192.168.86.29:8000/checkService", {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ serviceName })
      });
      const data = await response.json();
      this.shadowRoot.getElementById('status').textContent = 
        data.isRunning ? '✓ Running' : '✗ Stopped';
    } catch (error) {
      this.shadowRoot.getElementById('status').textContent = error.message;
    }
  }

  async stopService(serviceName){

    try{
            
      const response = await fetch("http://192.168.86.29:8000/stopService", {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ serviceName })
      });
      const data = await response.json();
      this.shadowRoot.getElementById('status').textContent = 
        data.isRunning ? '✓ Running' : '✗ Stopped';
      } catch (error) {
      this.shadowRoot.getElementById('status').textContent = error.message;
    }

      
    }

async startService(serviceName){

  try{
	  
    const response = await fetch("http://192.168.86.29:8000/startService", {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ serviceName })
    });
    const data = await response.json();
    this.shadowRoot.getElementById('status').textContent = 
      data.isRunning ? '✓ Running' : '✗ Stopped';
    } catch (error) {
    this.shadowRoot.getElementById('status').textContent = error.message;
  }

    
  }



}

customElements.define('service-card', ServiceCard);
