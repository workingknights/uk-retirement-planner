#!/bin/bash

# Cloudflare Deployment Helper Script
# This script helps you prepare your code for Cloudflare Pages and Workers.

echo "--- Preparing Cloudflare Deployment ---"

# 1. Build Frontend
echo "Building frontend..."
cd assets
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
echo "   - Build command: cd assets && npm install && npm run build"
echo "   - Build output directory: assets/dist"
echo "3. Add Environment Variable: VITE_API_URL = [Your Worker URL]"
echo ""
echo "B. Cloudflare Workers (Backend):"
echo "1. In your dashboard, Create a KV Namespace named 'SCENARIOS_KV'."
echo "2. Copy the Namespace ID and paste it into 'src/wrangler.toml'."
echo "3. Run 'cd src && npx wrangler deploy' to publish your API."
echo ""
echo "--- Preparation Complete ---"
