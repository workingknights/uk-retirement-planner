#!/bin/bash

# Deployment preparation script for UK Retirement Planner

echo "--- Preparing deployment assets ---"

# 1. Build Frontend
echo "Building frontend..."
cd frontend
npm install
npm run build
cd ..

# 2. Package together
echo "Packaging UI and API..."
cp -r frontend/dist backend/

# 3. Prepare Backend
echo "Verifying backend dependencies..."
cd backend
pip install -r requirements.txt
cd ..

echo "--- Preparation Complete ---"
echo ""
echo "NEXT STEPS FOR ALWAYSDATA.COM:"
echo "1. Upload 'backend' folder and 'frontend/dist' folder via FTP/SSH."
echo "2. Create a 'User program' web application in the alwaysdata dashboard."
echo "3. Use this command: uvicorn main:app --host 0.0.0.0 --port \$PORT"
echo "4. Set the 'Working directory' to the uploaded 'backend' folder."
echo "5. Create a 'Static files' web application for the 'dist' folder (mapped to /)."
echo "6. Set the environment variable ALLOWED_ORIGINS to include your alwaysdata domain."
echo ""
echo "Note: The current frontend expects the API at /api — ensure your routing matches."
