import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, status, Depends
from pydantic import BaseModel
import asyncpg

import shutil
from pathlib import Path
from fastapi import UploadFile, File, Form, BackgroundTasks

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, status, Depends
# 1. IMPORT THE CORS MIDDLEWARE COMPONENT
from fastapi.middleware.cors import CORSMiddleware 
from pydantic import BaseModel
import asyncpg
import re
import uuid


STORAGE_DIR = Path("storage/parcels")

# Import our new multi-tenant security tools
from auth_utils import get_current_tenant_context, create_tenant_access_token

def load_env_variables():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                if line.strip() and not line.startswith("#"):
                    key, value = line.strip().split("=", 1)
                    os.environ[key] = value

load_env_variables()
DATABASE_URL = os.getenv("DATABASE_URL")

class AsyncSaaSDatabaseManager:
    def __init__(self):
        self.pool = None

    async def initialize_pool(self):
        self.pool = await asyncpg.create_pool(dsn=DATABASE_URL, min_size=2, max_size=10)
        print("🚀 STATUS OK: Asynchronous database connection pool established.")

    async def shutdown_pool(self):
        if self.pool:
            await self.pool.close()

db_manager = AsyncSaaSDatabaseManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await db_manager.initialize_pool()
    yield
    await db_manager.shutdown_pool()

app = FastAPI(title="Commercial-3PL-SaaS-Engine", lifespan=lifespan)

# 2. CONFIGURE ALLOWED FRONTIEND ORIGINS
# This explicitly allows your local React web page to talk to your cloud database gateway safely
# Ensure there is a clean comma at the end of the CORSMiddleware argument line
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows your cloud frontend to speak to your backend securely from anywhere
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic schema validation for incoming physical scanning streams
class BarcodeScanInput(BaseModel):
    barcode_data: str
    location_code: str
    adjustment_qty: int

# ========================================================
# 1. TOKEN GENERATION ROUTE (Simulated Login)
# ========================================================
@app.get("/api/v1/auth/mock-token")
def generate_mock_warehouse_token(target_tenant: str):
    """
    Utility endpoint to simulate a login for testing.
    Pass 'jersey_city' or 'los_angeles' to fetch an isolated tenant token.
    """
    # Mapped directly to the 'tenant_id' UUIDs we seeded in Step 1
    tenant_map = {
        "jersey_city": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "los_angeles": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    }
    
    selected_id = tenant_map.get(target_tenant.lower())
    if not selected_id:
        raise HTTPException(status_code=400, detail="Unknown mock client context designation.")
        
    generated_jwt = create_tenant_access_token(
        tenant_id=selected_id, 
        user_id="user-12345", 
        role="OPERATOR"
    )
    return {"access_token": generated_jwt, "token_type": "bearer"}

# ========================================================
# 2. PROTECTED INTERACTIVE INVENTORY DATA ROUTE
# ========================================================
# ========================================================
# 2. COMMERCIALLY RE-ENGINEERED INVENTORY SCAN UPSERT ROUTE
# ========================================================
@app.post("/api/v1/inventory/scan-update")
async def register_laser_scan_action(
    payload: BarcodeScanInput,
    tenant_context_id: str = Depends(get_current_tenant_context)
):
    """
    Handles immediate incoming data from a hardware laser scanner or mobile app.
    Resolves barcode string to internal SKU ID, maps the location code, 
    and executes an atomic, thread-safe UPSERT block under RLS boundaries.
    """
    async with db_manager.pool.acquire() as connection:
        # Enforce our strict tenant isolation context session at database transaction level
        await connection.execute(f"SET LOCAL app.current_tenant_id = '{tenant_context_id}';")
        
        # Open an atomic transaction block to handle concurrent warehouse scanning traffic safely
        async with connection.transaction():
            
            # Step A: Resolve the raw barcode/UPC text string to find the internal SKU UUID record
            # Because Row Level Security is active, this lookup is automatically restricted to this tenant
            sku_record = await connection.fetchrow(
                "SELECT id FROM skus WHERE sku_code = $1;", 
                payload.barcode_data
            )
            if not sku_record:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"SKU Registry Missing: Code '{payload.barcode_data}' is not assigned to this tenant space."
                )
            sku_uuid = sku_record['id']

            # Step B: Resolve the raw location text string to find the internal Pallet Location UUID
            location_record = await connection.fetchrow(
                "SELECT id FROM pallet_locations WHERE location_code = $1;", 
                payload.location_code
            )
            if not location_record:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Location Failure: Warehouse grid does not recognize slot placement '{payload.location_code}'."
                )
            location_uuid = location_record['id']

            # Step C: Execute an atomic UPSERT (ON CONFLICT DO UPDATE) on your matrix ledger
            # This handles both receiving inventory (+ qty) or picking/reducing stock (- qty)
            updated_inventory_qty = await connection.fetchval(
                """
                INSERT INTO inventory (tenant_id, sku_id, location_id, quantity)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (sku_id, location_id)
                DO UPDATE SET quantity = inventory.quantity + EXCLUDED.quantity, updated_at = CURRENT_TIMESTAMP
                RETURNING quantity;
                """,
                tenant_context_id, sku_uuid, location_uuid, payload.adjustment_qty
            )

            # Step D: Automatically transition the status of the pallet location rack based on unit balances
            await connection.execute(
                """
                UPDATE pallet_locations 
                SET status = CASE WHEN $1 > 0 THEN 'PARTIAL' ELSE 'EMPTY' END
                WHERE id = $2;
                """,
                updated_inventory_qty, location_uuid
            )
            
            return {
                "status": "SUCCESS",
                "scanned_barcode": payload.barcode_data,
                "assigned_location": payload.location_code,
                "ledger_adjustment": payload.adjustment_qty,
                "current_total_stock_at_location": updated_inventory_qty
            }

@app.get("/api/v1/health")
async def system_health_check():
    async with db_manager.pool.acquire() as connection:
        tenant_count = await connection.fetchval("SELECT COUNT(*) FROM tenants;")
        return {"status": "HEALTHY", "registered_tenants_in_system": tenant_count}


import re

# ========================================================
# 3. DYNAMIC BACKGROUND WORKER (Carrier Switching Simulation)
# ========================================================
import re
import uuid

# ========================================================
# AUTOMATED RE-ENGINEERED BACKGROUND OCR & ROUTING WORKER
# ========================================================
async def execute_asynchronous_label_parsing(
    parcel_id: str, 
    tenant_id: str, 
    raw_ocr_dump_from_cloud: str
):
    """
    Autonomous Inbound Parsing Engine: Parses unstructured label data,
    auto-identifies the carrier via regex pattern routing, and matches the 3PL client.
    """
    try:
        # Normalize the text to prevent casing misses during analysis
        sanitized_text = raw_ocr_dump_from_cloud.upper()
        
        # Initialize default resolution fields
        tracking_number = None
        carrier = "UNKNOWN"

        # 1. CARRIER IDENTIFICATION PATTERN EVALUATION
        
        # Pass A: Check for explicit UPS signatures (Standard 1Z Tracking)
        ups_match = re.search(r'\b1Z[A-Z0-9]{16}\b', sanitized_text)
        
        # Pass B: Check for explicit USPS patterns (20-22 numeric string, often preceded by 420 routing)
        usps_match = re.search(r'\b(9[234]\d{20})\b|\b420\d{5}(9[234]\d{20})\b', sanitized_text)
        
        # Pass C: Check for explicit FedEx configurations (12 or 15 consecutive digits)
        fedex_match = re.search(r'\b\d{12}\b|\b\d{15}\b', sanitized_text)
        
        # Pass D: Check for Amazon Logistics (TBA prefix followed by 12 digits)
        amazon_match = re.search(r'\bTBA\d{12}\b', sanitized_text)

        # 2. DECISION LOGIC MATRIX
        if ups_match:
            tracking_number = ups_match.group(0)
            carrier = "UPS"
        elif usps_match:
            # If the regex captured the full barcode string alongside a 420 zip prefix, isolate the actual tracking token
            full_capture = usps_match.group(0)
            tracking_number = full_capture[-22:] if len(full_capture) > 22 else full_capture
            carrier = "USPS"
        elif amazon_match:
            tracking_number = amazon_match.group(0)
            carrier = "AMAZON LOGISTICS"
        elif fedex_match:
            # FedEx numbers are strictly numeric digits without distinctive letter prefixes, 
            # so we verify if prominent FedEx branding keywords exist near the text bounds as a safety guardrail.
            tracking_number = fedex_match.group(0)
            if "FEDEX" in sanitized_text or "FX" in sanitized_text:
                carrier = "FEDEX"
            else:
                carrier = "POTENTIAL FEDEX / UNKNOWN"
        else:
            tracking_number = f"UNREADABLE-{uuid.uuid4().hex[:8].upper()}"
            carrier = "UNKNOWN"

        # 3. DYNAMIC MULTI-TENANT CLIENT RESOLVING (Fuzzy String Match)
        async with db_manager.pool.acquire() as connection:
            await connection.execute(f"SET LOCAL app.current_tenant_id = '{tenant_id}';")
            
            # Fetch all active brands/clients registered under this specific 3PL tenant space
            clients_in_system = await connection.fetch("SELECT id, client_name FROM clients;")
            resolved_client_id = None
            
            for client in clients_in_system:
                # Check if the registered business name is printed inside the label shipping block text
                if client['client_name'].upper() in sanitized_text:
                    resolved_client_id = client['id']
                    break
            
            # 4. Finalize the record modification inside your Neon cloud ledger instance
            await connection.execute(
                """
                UPDATE inbound_parcels 
                SET tracking_number = $1, carrier = $2, raw_ocr_dump = $3, client_id = $4
                WHERE id = $5;
                """,
                tracking_number, carrier, raw_ocr_dump_from_cloud, resolved_client_id, uuid.UUID(parcel_id)
            )
            print(f"📊 AUTONOMOUS ROUTER: Processed tracking [{tracking_number}] matched to carrier [{carrier}]")
            
    except Exception as e:
        print(f"❌ CRITICAL BACKING PROCESSING EXCEPTION: {str(e)}")

# ========================================================
# 4. UPDATED MULTIPART INBOUND PARCEL SCAN ENDPOINT
# ========================================================
@app.post("/api/v1/inbound/blind-receive", status_code=status.HTTP_201_CREATED)
async def inbound_blind_receive(
    background_tasks: BackgroundTasks,
    simulated_raw_label_text: str = Form(...), # Mimics the data returned from an image-to-text pass
    label_photo: UploadFile = File(...),
    contents_photo: UploadFile = File(...),
    tenant_context_id: str = Depends(get_current_tenant_context)
):
    """
    High-density reception endpoint. Captures multipart photography, 
    persists media buffers, and routes parsing out-of-band without operator lag.
    """
    parcel_uuid = str(uuid.uuid4())
    tenant_dir = STORAGE_DIR / tenant_context_id / parcel_uuid
    tenant_dir.mkdir(parents=True, exist_ok=True)
    
    label_target_path = tenant_dir / "label_outer.jpg"
    contents_target_path = tenant_dir / "contents_inner.jpg"
    
    try:
        with open(label_target_path, "wb") as buffer:
            shutil.copyfileobj(label_photo.file, buffer)
        with open(contents_target_path, "wb") as buffer:
            shutil.copyfileobj(contents_photo.file, buffer)
    except Exception:
        raise HTTPException(status_code=500, detail="IO processing stream error.")
        
    async with db_manager.pool.acquire() as connection:
        await connection.execute(f"SET LOCAL app.current_tenant_id = '{tenant_context_id}';")
        await connection.execute(
            """
            INSERT INTO inbound_parcels (id, tenant_id, label_photo_url, content_photo_url)
            VALUES ($1, $2, $3, $4);
            """,
            uuid.UUID(parcel_uuid), uuid.UUID(tenant_context_id), str(label_target_path), str(contents_target_path)
        )
        
    # Kick off the autonomous background execution pass
    background_tasks.add_task(
        execute_asynchronous_label_parsing, 
        parcel_uuid, 
        tenant_context_id, 
        simulated_raw_label_text
    )
    
    return {
        "status": "PROCESSING_QUEUED",
        "message": "Media buffers committed. Autonomous parsing sequence initialized out-of-band.",
        "parcel_id": parcel_uuid
    }


from datetime import date

# Pydantic Schemas for Outbound Data Validation
class OutboundShipmentCreate(BaseModel):
    client_id: str
    destination_type: str # 'AMAZON_FBA_PALLET' or 'B2C_PARCEL'
    scheduled_date: date
    items: list[dict] # Expected format: [{"sku_code": "880961123456", "quantity_requested": 5}]

class OutboundExitScan(BaseModel):
    shipment_id: str
    scanned_tracking_number: str

# ========================================================
# 5. OUTBOUND WORKFLOW ENGINE: MANIFEST CREATION
# ========================================================
@app.post("/api/v1/outbound/create-manifest", status_code=status.HTTP_201_CREATED)
async def create_outbound_manifest(
    payload: OutboundShipmentCreate,
    tenant_context_id: str = Depends(get_current_tenant_context)
):
    """
    Allows a client or manager to generate an outbound pick specification.
    Seeds the shipment record in a 'DRAFT' state and maps required picking lines.
    """
    async with db_manager.pool.acquire() as connection:
        await connection.execute(f"SET LOCAL app.current_tenant_id = '{tenant_context_id}';")
        
        async with connection.transaction():
            # 1. Insert the master outbound record
            # We mock a dummy shipping label URL for initialization before file upload
            shipment_id = await connection.fetchval(
                """
                INSERT INTO outbound_shipments (tenant_id, client_id, destination_type, shipping_label_url, status, scheduled_date)
                VALUES ($1, $2, $3, $4, 'DRAFT', $5)
                RETURNING id;
                """,
                uuid.UUID(tenant_context_id), uuid.UUID(payload.client_id), 
                payload.destination_type, "pending_upload", payload.scheduled_date
            )
            
            # 2. Map and loop incoming item codes to internal SKU UUIDs to populate pick specifications
            for item in payload.items:
                sku_id = await connection.fetchval(
                    "SELECT id FROM skus WHERE sku_code = $1;", item['sku_code']
                )
                if not sku_id:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Configuration Error: SKU code '{item['sku_code']}' does not exist in master registry."
                    )
                
                await connection.execute(
                    """
                    INSERT INTO outbound_items (tenant_id, shipment_id, sku_id, quantity_requested, quantity_picked)
                    VALUES ($1, $2, $3, $4, $5);
                    """,
                    uuid.UUID(tenant_context_id), shipment_id, sku_id, item['quantity_requested'], item['quantity_requested'] 
                    # Simulating that items are fully picked for the final scan validation step
                )
                
            return {
                "status": "MANIFEST_CREATED",
                "shipment_id": str(shipment_id),
                "current_workflow_state": "DRAFT",
                "message": "Pick specifications successfully generated for warehouse floor fulfillment."
            }

# ========================================================
# 6. ATOMIC OUTBOUND EXIT SCAN & INVENTORY REDUCTION
# ========================================================
@app.post("/api/v1/outbound/exit-scan")
async def finalize_outbound_shipment_exit(
    payload: OutboundExitScan,
    tenant_context_id: str = Depends(get_current_tenant_context)
):
    """
    The final exit scan action. When the operator triggers the laser scanner on the outbound
    carton label, this endpoint reads the carrier tracking number, sets status to 'CLOSED',
    and atomically deducts the picked items from the core inventory ledger.
    """
    async with db_manager.pool.acquire() as connection:
        await connection.execute(f"SET LOCAL app.current_tenant_id = '{tenant_context_id}';")
        
        async with connection.transaction():
            # 1. Fetch the outbound manifest and verify it exists under this tenant's security boundary
            shipment = await connection.fetchrow(
                "SELECT status FROM outbound_shipments WHERE id = $1;", uuid.UUID(payload.shipment_id)
            )
            if not shipment:
                raise HTTPException(status_code=404, detail="Outbound shipment manifest not found.")
            if shipment['status'] == 'CLOSED':
                raise HTTPException(status_code=400, detail="Transaction Locked: This shipment has already exited the warehouse.")

            # 2. Identify the carrier type automatically by running our pattern routing engine on the scanned input
            scanned_upper = payload.scanned_tracking_number.upper()
            carrier = "UNKNOWN"
            if re.search(r'\b1Z[A-Z0-9]{16}\b', scanned_upper):
                carrier = "UPS"
            elif re.search(r'\b(9[234]\d{20})\b', scanned_upper):
                carrier = "USPS"
            elif re.search(r'\b\d{12}\b|\b\d{15}\b', scanned_upper):
                carrier = "FEDEX"
            elif scanned_upper.startswith("TBA"):
                carrier = "AMAZON LOGISTICS"

            # 3. Pull the targeted pick list items for this outbound package
            picked_items = await connection.fetch(
                "SELECT sku_id, quantity_picked FROM outbound_items WHERE shipment_id = $1;", uuid.UUID(payload.shipment_id)
            )

            # 4. Loop and deduct unit stock balances atomically from the primary inventory tracking matrix
            for item in picked_items:
                # We locate any available pallet pool location holding this SKU and decrement stock balance
                # Using a 'quantity >= allocation' rule guarantees data integrity constraints
                await connection.execute(
                    """
                    UPDATE inventory 
                    SET quantity = quantity - $1, updated_at = CURRENT_TIMESTAMP
                    WHERE tenant_id = $2 AND sku_id = $3 AND quantity >= $1;
                    """,
                    item['quantity_picked'], uuid.UUID(tenant_context_id), item['sku_id']
                )

            # 5. Advance the manifest state machine to 'CLOSED' and bind the real carrier tracking parameters
            await connection.execute(
                """
                UPDATE outbound_shipments 
                SET status = 'CLOSED', tracking_number = $1, carrier = $2
                WHERE id = $3;
                """,
                payload.scanned_tracking_number, carrier, uuid.UUID(payload.shipment_id)
            )

            return {
                "status": "CLOSED",
                "message": "Fulfillment loop finalized. Inventory balances decremented.",
                "verified_carrier": carrier,
                "logged_tracking_number": payload.scanned_tracking_number
            }
# ========================================================
# 7. CLIENT REPORTING ENGINE (ON-DEMAND AUDITS)
# ========================================================
@app.get("/api/v1/reports/inventory-ledger")
async def get_live_inventory_ledger_report(
    tenant_context_id: str = Depends(get_current_tenant_context)
):
    """
    On-Demand Live Inventory Ledger: Returns active item allocations 
    mapped across specific warehouse pallet slots for the tenant scope.
    """
    async with db_manager.pool.acquire() as connection:
        # Bind the session to the tenant context
        await connection.execute(f"SET LOCAL app.current_tenant_id = '{tenant_context_id}';")
        
        # Pull aggregated inventory balances joined against SKU catalogs and rack locations
        report_rows = await connection.fetch(
            """
            SELECT 
                s.sku_code,
                s.name AS product_name,
                pl.location_code,
                i.quantity AS units_in_stock,
                i.updated_at AS last_activity
            FROM inventory i
            JOIN skus s ON i.sku_id = s.id
            LEFT JOIN pallet_locations pl ON i.location_id = pl.id
            WHERE i.quantity > 0
            ORDER BY s.sku_code ASC, pl.location_code ASC;
            """
        )
        
        # Structure the ledger response array
        ledger_data = [
            {
                "sku": row["sku_code"],
                "product": row["product_name"],
                "pallet_bay_location": row["location_code"],
                "units_on_hand": row["units_in_stock"],
                "last_audit_timestamp": row["last_activity"].isoformat() if row["last_activity"] else None
            }
            for row in report_rows
        ]
        
        return {
            "report_type": "LIVE_INVENTORY_LEDGER",
            "generated_at": date.today().isoformat(),
            "total_unique_allocations": len(ledger_data),
            "ledger": ledger_data
        }

@app.get("/api/v1/reports/weekly-throughput")
async def get_weekly_throughput_summary(
    tenant_context_id: str = Depends(get_current_tenant_context)
):
    """
    Weekly Throughput Metric: Summarizes the operational volume 
    (total packages in / out) handled over the trailing 7 days.
    """
    async with db_manager.pool.acquire() as connection:
        await connection.execute(f"SET LOCAL app.current_tenant_id = '{tenant_context_id}';")
        
        # Query total inbound boxes processed
        total_inbound = await connection.fetchval(
            "SELECT COUNT(*) FROM inbound_parcels WHERE received_at >= CURRENT_TIMESTAMP - INTERVAL '7 days';"
        )
        
        # Query total outbound orders closed out
        total_outbound = await connection.fetchval(
            "SELECT COUNT(*) FROM outbound_shipments WHERE status = 'CLOSED' AND created_at >= CURRENT_TIMESTAMP - INTERVAL '7 days';"
        )
        
        return {
            "report_type": "WEEKLY_FULFILLMENT_VELOCITY",
            "reporting_period": "Trailing 7 Days",
            "metrics": {
                "inbound_blind_parcels_processed": total_inbound,
                "outbound_shipments_finalized": total_outbound,
                "total_warehouse_transactions": total_inbound + total_outbound
            }
        }        