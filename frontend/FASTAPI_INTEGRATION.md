# FastAPI Backend Integration

## Overview
Successfully integrated the frontend with the GemmaFinOS FastAPI backend hosted at `http://localhost:8000`. This document outlines the changes made and how to test the integration.

## Changes Made

### 1. API Client Updates (`lib/api.ts`)
- ✅ Updated base URL to use the local backend endpoint
- ✅ Added appropriate CORS headers
- ✅ Implemented all FastAPI endpoints based on your OpenAPI spec:
  - `/` - Health check
  - `/case-types` - Get available case types
  - `/jurisdictions` - Get available jurisdictions
  - `/matters` - Create new matter (POST with FormData)
  - `/matters/{matter_id}/documents` - Upload documents (POST with FormData)
  - `/chat` - Send initial chat message (POST with FormData)
  - `/chat-followup` - Send follow-up messages (POST with FormData)
  - `/runs/{run_id}` - Get run details
  - `/runs/{run_id}/export` - Export run results
  - `/test-arbiter` - Test the DAO arbiter system
  - `/conversation/{matter_id}` - Get/clear conversation history
  - `/conversation/{matter_id}/export` - Export conversation

### 2. API Route Updates
- ✅ Updated `/api/chat/citations/route.ts` to proxy to FastAPI backend
- ✅ Updated `/api/chat/llm/route.ts` to handle initial and follow-up messages
- ✅ Created `/api/case-types/route.ts` with fallback data
- ✅ Created `/api/jurisdictions/route.ts` with fallback data

### 3. Component Updates
- ✅ **Chat Page** (`app/chat/page.tsx`):
  - Auto-creates matter when chat starts
  - Tracks run IDs for follow-up messages
  - Passes matter ID to API calls
  - Handles both initial and follow-up chat messages

- ✅ **Chat Input** (`components/chat/ChatInput.tsx`):
  - Loads case types and jurisdictions from API
  - Falls back to static data if API unavailable
  - Changed jurisdiction from text input to dropdown

- ✅ **Matter Creation** (`components/matters/MatterCreationForm.tsx`):
  - Updated to use new FastAPI matter creation endpoint
  - Removed language parameter (not in FastAPI spec)

### 4. New Features
- ✅ **API Test Page** (`app/api-test/page.tsx`):
  - Comprehensive testing interface for all endpoints
  - Real-time API testing with results display
  - Easy access to test individual endpoints

## How to Test

### 1. Environment Setup
Create a `.env.local` file in the frontend root with:
```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### 2. Test the Integration

#### Option A: Use the Test Page
1. Navigate to `/api-test` in your browser
2. Run each test individually to verify endpoints
3. Check the JSON responses for each endpoint
4. For chat testing, first create a matter and copy the ID

#### Option B: Use the Chat Interface
1. Navigate to `/chat` 
2. Select a case type and jurisdiction
3. Enter a legal question
4. Verify the response comes from your FastAPI backend
5. Try follow-up questions to test conversation flow

### 3. Expected Flow
1. **Chat Start**: Frontend creates a new matter automatically
2. **First Message**: Sent to `/chat` endpoint with matter_id, case_type, and jurisdiction
3. **Backend Processing**: Your FastAPI processes with DAO agents
4. **Response**: Frontend displays DAO verdict with agent analysis
5. **Follow-up**: Subsequent messages use `/chat-followup` with run_id
6. **Citations**: Extracted from backend response and displayed in sidebar

## API Request Formats

### Chat Message (Initial)
```javascript
// Sent as FormData to /chat
{
  matter_id: "string",
  message: "string", 
  case_type: "string",
  jurisdiction_region: "string"
}
```

### Chat Follow-up
```javascript
// Sent as FormData to /chat-followup  
{
  matter_id: "string",
  run_id: "string",
  message: "string"
}
```

### Matter Creation
```javascript
// Sent as FormData to /matters
{
  title: "string"
}
```

### Document Upload
```javascript
// Sent as FormData to /matters/{matter_id}/documents
{
  file: File,
  court: "string" (optional),
  case_number: "string" (optional)
}
```

## Error Handling
- ✅ All API calls include proper error handling
- ✅ Fallback data for case types/jurisdictions if backend unavailable  
- ✅ User-friendly error messages in chat interface
- ✅ Network error recovery and retry logic

## CORS and Headers
- ✅ Proper CORS headers configured for all requests
- ✅ Proper FormData handling for FastAPI multipart endpoints
- ✅ Content-Type headers automatically set by browser for FormData

## Next Steps
1. Test all endpoints using the `/api-test` page
2. Verify chat functionality with real legal questions
3. Test document uploading in matter workspace
4. Monitor console for any remaining API errors
5. Configure production backend URL when ready

## Troubleshooting
- **CORS Errors**: Ensure the GemmaFinOS backend is running and accessible
- **422 Validation Errors**: Check FastAPI logs for field validation issues  
- **Network Errors**: Verify backend is running and the API URL is correct
- **Empty Responses**: Check if FastAPI responses match expected format

The integration is now complete and ready for testing! 🚀
