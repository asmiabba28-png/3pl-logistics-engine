
import React, { useState, useEffect } from 'react';
const API_BASE_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

function App() {
    const [tenantToken, setTenantToken] = useState("");
    const [selectedTenant, setSelectedTenant] = useState("jersey_city");
    const [lastScannedBarcode, setLastScannedBarcode] = useState("Awaiting First Laser Trigger...");
    const [locationCode, setLocationCode] = useState("BAY-A-01-P3");
    const [adjustmentQty, setAdjustmentQty] = useState(1);
    const [scannerBuffer, setScannerBuffer] = useState("");
    const [systemLogs, setSystemLogs] = useState([]);

    const playSound = (type) => {
        try {
            const ctx = new (window.AudioContext || window.webkitAudioContext)();
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.connect(gain);
            gain.connect(ctx.destination);
            
            if (type === "success") {
                osc.frequency.setValueAtTime(880, ctx.currentTime); 
                gain.gain.setValueAtTime(0.1, ctx.currentTime);
                osc.start();
                osc.stop(ctx.currentTime + 0.1);
            } else {
                osc.frequency.setValueAtTime(220, ctx.currentTime); 
                gain.gain.setValueAtTime(0.2, ctx.currentTime);
                osc.start();
                osc.stop(ctx.currentTime + 0.3);
            }
        } catch(e) { console.log("Audio play blocked"); }
    };

    useEffect(() => {
        fetch(`${API_BASE_URL}/api/v1/auth/mock-token?target_tenant=${selectedTenant}`)
            .then(res => res.json())
            .then(data => {
                setTenantToken(data.access_token);
                logAction(`Security context mapped to tenant: ${selectedTenant.toUpperCase()}`, "info");
            })
            .catch(() => logAction("Security initialization failed. Verify backend is running.", "error"));
    }, [selectedTenant]);

    useEffect(() => {
        let localBuffer = "";
        let lastKeyTime = Date.now();

        const handleGlobalKeyPress = (e) => {
            const currentTime = Date.now();
            if (currentTime - lastKeyTime > 200) localBuffer = "";
            lastKeyTime = currentTime;

            if (e.key === "Enter") {
                if (localBuffer.trim().length > 0) {
                    processAutomatedBarcode(localBuffer.trim());
                    localBuffer = "";
                }
            } else if (e.key.length === 1) {
                localBuffer += e.key;
            }
        };

        window.addEventListener("keydown", handleGlobalKeyPress);
        return () => window.removeEventListener("keydown", handleGlobalKeyPress);
    }, [tenantToken, locationCode, adjustmentQty]);

    const logAction = (msg, level = "info") => {
        setSystemLogs(prev => [{ time: new Date().toLocaleTimeString(), msg, level }, ...prev.slice(0, 9)]);
    };

    const processAutomatedBarcode = async (barcode) => {
        if (!tenantToken) {
            logAction("Cannot scan: Security token missing.", "error");
            return;
        }
        setLastScannedBarcode(barcode);
        logAction(`Laser Read Detected: [${barcode}]`, "info");

        try {
            const response = await fetch(`${API_BASE_URL}/api/v1/inventory/scan-update`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${tenantToken}`
                },
                body: JSON.stringify({
                    barcode_data: barcode,
                    location_code: locationCode,
                    adjustment_qty: parseInt(adjustmentQty)
                })
            });

            const data = await response.json();
            if (response.ok) {
                playSound("success");
                logAction(`Ledger Synchronized. Stock: ${data.current_total_stock_at_location}`, "success");
            } else {
                playSound("error");
                logAction(`Routing Failure: ${data.detail || "Unknown error"}`, "error");
            }
        } catch (err) {
            playSound("error");
            logAction("Network Interruption: Backend unreachable.", "error");
        }
    };

    return (
        <div className="max-w-md mx-auto min-h-screen flex flex-col bg-slate-950 text-slate-100 shadow-2xl border-x border-slate-800 font-sans antialiased">
            <header className="p-4 bg-slate-900 border-b border-slate-800 flex justify-between items-center">
                <div>
                    <h1 className="text-lg font-bold text-sky-400 tracking-wide">3PL SCAN ENGINE</h1>
                    <span className="text-xs text-slate-400">v1.0.0 Commercial Core</span>
                </div>
                <div className="flex items-center space-x-2">
                    <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse"></span>
                    <span className="text-xs text-slate-300 font-mono">LASER_READY</span>
                </div>
            </header>

            <div className="p-3 bg-slate-900/50 border-b border-slate-800 flex space-x-2 text-xs">
                <button 
                    onClick={() => setSelectedTenant("jersey_city")}
                    className={`flex-1 py-1.5 rounded font-medium transition ${selectedTenant === "jersey_city" ? 'bg-sky-600 text-white shadow' : 'bg-slate-800 text-slate-400'}`}>
                    Jersey City Hub
                </button>
                <button 
                    onClick={() => setSelectedTenant("los_angeles")}
                    className={`flex-1 py-1.5 rounded font-medium transition ${selectedTenant === "los_angeles" ? 'bg-sky-600 text-white shadow' : 'bg-slate-800 text-slate-400'}`}>
                    LA Port Hub
                </button>
            </div>

            <main className="flex-1 p-4 space-y-4">
              {/* Add this block right inside your <main className="flex-1 p-4 space-y-4"> container */}
              <div className="bg-slate-900/40 p-4 border border-slate-800/80 rounded-xl space-y-3">
                  <div className="text-xs font-bold text-slate-400 uppercase tracking-wider">Inbound Parcel Photo Capture Tray</div>
                  
                  <div className="grid grid-cols-2 gap-2">
                      {/* Outer Label Photo Target */}
                      <label className="flex flex-col items-center justify-center p-3 bg-slate-950 border border-dashed border-slate-700 rounded-lg cursor-pointer hover:border-sky-500 transition">
                          <span className="text-xs font-semibold text-slate-300">📸 Outer Label</span>
                          <span className="text-[10px] text-slate-500 mt-1">Tap to take photo</span>
                          <input 
                              type="file" 
                              accept="image/*" 
                              capture="environment" /* Forces mobile browser to open the rear-facing camera directly */
                              className="hidden" 
                              onChange={(e) => logAction(`Outer label photo captured: ${e.target.files[0]?.name}`, "info")}
                          />
                      </label>

                      {/* Inner Contents Photo Target */}
                      <label className="flex flex-col items-center justify-center p-3 bg-slate-950 border border-dashed border-slate-700 rounded-lg cursor-pointer hover:border-sky-500 transition">
                          <span className="text-xs font-semibold text-slate-300">📦 Inner Box Contents</span>
                          <span className="text-[10px] text-slate-500 mt-1">Tap to take photo</span>
                          <input 
                              type="file" 
                              accept="image/*" 
                              capture="environment" 
                              className="hidden" 
                              onChange={(e) => logAction(`Contents photo captured: ${e.target.files[0]?.name}`, "info")}
                          />
                      </label>
                  </div>

                  {/* Simulation Trigger Button */}
                  <button 
                      onClick={() => {
                          logAction("Streaming multipart image frames to FastAPI pipeline...", "info");
                          playSound("success");
                          logAction("Inbound Engine Auto-Deduction Complete: Routed to USPS", "success");
                      }}
                      className="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-bold py-2 px-4 rounded text-xs tracking-wider uppercase transition">
                      Process Blind Arrival Ingest
                  </button>
              </div>              
                <div className="p-5 bg-slate-900 border border-slate-800 rounded-xl text-center shadow-inner relative overflow-hidden">
                    <div className="text-xs font-semibold text-slate-400 mt-2">LAST CAPTURED VALUE</div>
                    <div className="text-2xl font-mono font-black text-sky-400 tracking-wider my-2 truncate">{lastScannedBarcode}</div>
                    <p className="text-[10px] text-slate-400 bg-slate-950/80 p-2 rounded border border-slate-800 font-medium">
                        💡 <span className="text-amber-400">Continuous Focus Active:</span> Press your scanner trigger anytime.
                    </p>
                </div>

                <div className="space-y-3 bg-slate-900/40 p-4 border border-slate-800/80 rounded-xl">
                    <div>
                        <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">Target Rack Location Code</label>
                        <input 
                            type="text" 
                            value={locationCode} 
                            onChange={(e) => setLocationCode(e.target.value.toUpperCase())}
                            className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 text-sm font-mono text-emerald-400 focus:outline-none focus:border-emerald-500 transition"
                        />
                    </div>
                    <div>
                        <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">Volumetric Adjustment Qty</label>
                        <div className="flex items-center space-x-2">
                            <input 
                                type="number" 
                                value={adjustmentQty} 
                                onChange={(e) => setAdjustmentQty(e.target.value)}
                                className="w-24 bg-slate-950 border border-slate-800 rounded px-3 py-2 text-sm font-mono text-white focus:outline-none focus:border-sky-500"
                            />
                            <span className="text-xs text-slate-400 font-medium">Units per scan</span>
                        </div>
                    </div>
                </div>

                <div className="flex flex-col bg-slate-950 border border-slate-800 rounded-xl overflow-hidden h-48">
                    <div className="p-2 bg-slate-900 border-b border-slate-800 text-xs font-bold text-slate-400 flex justify-between items-center">
                        <span>LIVE DEVICE ACTIVITY TELEMETRY</span>
                        <button onClick={() => setSystemLogs([])} className="text-[10px] text-sky-500 hover:underline">Clear</button>
                    </div>
                    <div className="p-3 text-xs font-mono space-y-2 overflow-y-auto flex-1">
                        {systemLogs.length === 0 && <p className="text-slate-600 italic text-center pt-8">Console idle. Scan items to stream transactions.</p>}
                        {systemLogs.map((log, i) => (
                            <div key={i} className="flex items-start space-x-2">
                                <span className="text-slate-500 shrink-0">[{log.time}]</span>
                                <span className={log.level === 'error' ? 'text-rose-400 font-semibold' : log.level === 'success' ? 'text-emerald-400' : 'text-slate-300'}>
                                    {log.msg}
                                </span>
                            </div>
                        ))}
                    </div>
                </div>
            </main>

            <footer className="p-3 bg-slate-900 border-t border-slate-800">
                <div className="text-[10px] font-bold text-slate-500 mb-1.5 uppercase text-center tracking-wider">Laptop Keyboard Laser Wedge Simulator</div>
                <div className="flex space-x-2">
                    <input 
                        type="text" 
                        placeholder="Type barcode + click enter to mimic scan" 
                        value={scannerBuffer}
                        onChange={(e) => setScannerBuffer(e.target.value)}
                        onKeyDown={(e) => {
                            if(e.key === 'Enter') {
                                processAutomatedBarcode(scannerBuffer);
                                setScannerBuffer("");
                            }
                        }}
                        className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-1.5 text-xs text-slate-300 placeholder-slate-600 focus:outline-none focus:border-sky-500"
                    />
                </div>
            </footer>
        </div>
    );
}

export default App;
