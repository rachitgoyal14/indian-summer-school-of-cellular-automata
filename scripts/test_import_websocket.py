#!/usr/bin/env python3
"""
Test the WebSocket import_region flow to verify the backend is responding correctly.
"""
import sys
import os
import asyncio
import json

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from fastapi import FastAPI
from fastapi.websockets import WebSocket
import websockets

async def test_import():
    """Connect to the WebSocket server and test import_region."""
    uri = "ws://localhost:8000/ws"
    
    print("Connecting to WebSocket server...")
    try:
        async with websockets.connect(uri) as websocket:
            print("✓ Connected")
            
            # Wait for initial network message
            initial_msg = await websocket.recv()
            initial_data = json.loads(initial_msg)
            print(f"✓ Received initial message: {initial_data.get('type')}")
            
            # Send import_region request
            print("\nSending import_region request for 'IIT BHU Varanasi'...")
            await websocket.send(json.dumps({
                "type": "import_region",
                "place_name": "IIT BHU Varanasi"
            }))
            
            # Wait for responses (should get import_result, network, and state)
            messages_received = []
            timeout = 30  # 30 seconds timeout for Overpass API
            
            try:
                for i in range(5):  # Expect at least 3 messages
                    msg = await asyncio.wait_for(websocket.recv(), timeout=timeout)
                    data = json.loads(msg)
                    msg_type = data.get('type')
                    messages_received.append(msg_type)
                    print(f"  {i+1}. Received: {msg_type}")
                    
                    if msg_type == "import_result":
                        print(f"     → ok={data.get('ok')}, error={data.get('error')}")
                        if data.get('ok'):
                            print(f"     → roads={data.get('roads')}, junctions={data.get('junctions')}, cells={data.get('total_cells')}")
                    elif msg_type == "network":
                        print(f"     → {len(data.get('roads', []))} roads, {len(data.get('junctions', []))} junctions")
                    elif msg_type == "state":
                        print(f"     → step={data.get('step')}, running={data.get('running')}")
            except asyncio.TimeoutError:
                print(f"\n⚠ Timeout after {timeout}s waiting for messages")
            
            print(f"\nMessages received: {messages_received}")
            
            # Verify we got all expected messages
            if "import_result" in messages_received:
                print("✓ import_result received")
            else:
                print("✗ import_result NOT received")
            
            if "network" in messages_received:
                print("✓ network message received (frontend should update)")
            else:
                print("✗ network message NOT received (THIS IS THE BUG)")
            
            if "state" in messages_received:
                print("✓ state message received")
            else:
                print("✗ state message NOT received")
            
    except ConnectionRefusedError:
        print("✗ Could not connect - is the backend server running?")
        print("  Start it with: cd backend && python scripts/run_server.py")
    except Exception as e:
        print(f"✗ Error: {e}")

if __name__ == "__main__":
    print("="*70)
    print("WebSocket import_region Flow Test")
    print("="*70)
    print("\nThis test verifies that import_region sends all required messages.")
    print("If the frontend is stuck on 'Importing...', one of these messages")
    print("is likely not being sent.\n")
    
    asyncio.run(test_import())
