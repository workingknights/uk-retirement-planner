#!/bin/bash

# Cloudflare Deployment Helper Script
# This script helps you prepare your code for Cloudflare Pages and Workers.

echo "--- Preparing Cloudflare Deployment ---"

# 1. Build Frontend
echo "Building frontend..."
cd frontend
npm install
npm run build
cd ..

# 2. Instructions for Cloudflare Dashboard
echo ""
echo "NEXT STEPS FOR CLOUDFLARE:"
echo ""
echo "A. Cloudflare Pages (Frontend):"
echo "1. Create a new Pages project and connect your GitHub repo."
echo "2. Build Settings:"
echo "   - Framework preset: Vite"
echo "   - Build command: cd frontend && npm install && npm run build"
echo "   - Build output directory: frontend/dist"
echo "3. Add Environment Variable: VITE_API_URL = [Your Worker URL]"
echo ""
echo "B. Cloudflare Workers (Backend):"
echo "1. In your dashboard, Create a KV Namespace named 'SCENARIOS_KV'."
echo "2. Copy the Namespace ID and paste it into 'backend/wrangler.toml'."
echo "3. Run 'cd backend && npx wrangler deploy' to publish your API."
echo ""
echo "--- Preparation Complete ---"
