#!/bin/bash

# GemmaFinOS Server - Start Both Backend and Frontend

echo "🚀 Starting GemmaFinOS Server (Backend + Frontend)..."

# Function to check if a port is in use
check_port() {
    if lsof -Pi :$1 -sTCP:LISTEN -t >/dev/null ; then
        echo "⚠️  Port $1 is already in use"
        return 1
    else
        return 0
    fi
}

# Check ports
echo "🔍 Checking ports..."
check_port 8001 || { echo "❌ Backend port 8001 is busy"; exit 1; }
check_port 3001 || { echo "❌ Frontend port 3001 is busy"; exit 1; }

echo "✅ Ports are available"

# Start backend in background
echo "🔧 Starting backend server..."
cd "$(dirname "$0")/backend"
python start.py &
BACKEND_PID=$!

# Wait for backend to start
echo "⏳ Waiting for backend to initialize..."
sleep 5

# Check if backend is running
if kill -0 $BACKEND_PID 2>/dev/null; then
    echo "✅ Backend started successfully (PID: $BACKEND_PID)"
else
    echo "❌ Backend failed to start"
    exit 1
fi

# Start frontend
echo "🌐 Starting frontend..."
cd ../frontend
npm run dev &
FRONTEND_PID=$!

echo "✅ Frontend started (PID: $FRONTEND_PID)"

# Cleanup function
cleanup() {
    echo "🛑 Shutting down servers..."
    kill $BACKEND_PID 2>/dev/null
    kill $FRONTEND_PID 2>/dev/null
    echo "✅ Servers stopped"
    exit 0
}

# Handle Ctrl+C
trap cleanup SIGINT SIGTERM

echo ""
echo "🎉 GemmaFinOS Server is running!"
echo "📊 Backend:  http://localhost:8001"
echo "🌐 Frontend: http://localhost:3001"
echo "📚 API Docs: http://localhost:8001/docs"
echo ""
echo "Press Ctrl+C to stop both servers"

# Keep script running
wait
