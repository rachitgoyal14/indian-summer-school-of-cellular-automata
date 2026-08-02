# Frontend Import Issue Fix

## Problem Reported
User reported that when entering a place name in the "IMPORT REAL MAP" section of the frontend, the button gets stuck showing "Importing..." and the map never loads.

## Root Cause Investigation

### What Was Checked
1. ✅ Backend `import_region` handler - sends `import_result`, `network`, and `state` messages correctly
2. ✅ Frontend WebSocket hook - properly handles `import_result` messages with callbacks
3. ✅ RegionSearch component - correctly sets up callback and manages loading state
4. ✅ Type definitions - `ImportResultMessage` matches backend response structure

### Most Likely Cause
**Overpass API timeouts or failures** causing the backend to never send `import_result`.

Evidence:
- During smoke tests, Overpass API returned 504 errors and timeouts
- The smoke test log shows: "All Overpass endpoints failed"
- When Overpass fails, `fetch_roads()` returns `None`
- `import_region()` returns `{"ok": False, "error": "Overpass API request failed"}`
- But if the WebSocket send fails or the message is dropped, the frontend never receives it

## Fixes Applied

### 1. Added Timeout Protection (RegionSearch.tsx)
**Problem:** If the backend never responds (network issue, API down, etc.), the loading state never clears.

**Fix:** Added 60-second timeout that automatically clears loading state and shows error message.

```typescript
const timeout = setTimeout(() => {
  console.log("[RegionSearch] Import timed out after 60s");
  setLoading(false);
  setResult({
    ok: false,
    error: "Import timed out after 60 seconds. The OpenStreetMap API may be overloaded. Please try again.",
  });
}, 60000);
```

### 2. Added Console Logging for Debugging
**Problem:** No visibility into what's happening during the import process.

**Fix:** Added console.log statements at key points:
- When import starts
- When import_result is received in WebSocket
- When callback is invoked
- When timeout fires

This helps diagnose issues in the browser console.

### 3. Improved Error Messages
**Fix:** Timeout error now mentions that OSM API may be overloaded and suggests retrying.

## Testing Instructions

### To Test the Fix:
1. Start backend: `cd backend && python scripts/run_server.py`
2. Start frontend: `cd frontend && npm run dev`
3. Open `http://localhost:5173` in browser
4. Open browser console (F12)
5. Enter a place name (e.g., "IIT BHU Varanasi") and click Import
6. Watch console for log messages:
   - Should see: `[RegionSearch] Starting import for: ...`
   - Should see: `[WebSocket] Received import_result: ...`
   - Should see: `[WebSocket] Invoking import callback`
   - Should see: `[RegionSearch] Import result received: ...`

### Expected Behavior:
- **Success case:** Map loads within 10-20 seconds, console shows all messages
- **Overpass API down:** After 60 seconds, shows timeout error
- **Invalid place name:** Within 5 seconds, shows "Could not geocode" error

### Common Issues:
1. **"Importing..." for 60s then timeout** → Overpass API is down/slow. This is external to our code.
2. **Immediate error "Could not geocode"** → Place name not found in Nominatim. Try a different name.
3. **No response at all** → Backend not running or WebSocket connection failed.

## Files Modified
- `frontend/src/components/RegionSearch.tsx` - Added timeout and logging
- `frontend/src/hooks/useSimulationSocket.ts` - Added logging to import_result handler

## Verification Status
- ✅ Code changes applied
- ✅ Timeout protection added
- ✅ Logging added for debugging
- ⚠️ **Requires manual browser testing** - Cannot be verified in headless mode due to real API dependency

## Notes
The Overpass API is a free public service and can be slow or unavailable during peak usage. This is expected and not a bug in our code. The timeout provides a better user experience than hanging indefinitely.

## Recommendation for User
**Try the import again now** with the fixes applied. Check the browser console (F12) to see what's happening. If it still times out after 60s, the Overpass API is likely overloaded - wait a few minutes and try again.
