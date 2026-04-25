# Project Rules for UK Retirement Planner

## Workflow
- **Commit & Push**: After completing a task or a significant set of changes requested by the user, **ALWAYS commit the changes** with a descriptive message and **push them to the `main` branch**. This triggers the CI/CD pipeline for GCP/Firebase deployment, allowing the user to test the live version.
- **Frontend Development**: All frontend code is in the `assets/` directory. When running commands related to the frontend (like `npm run dev` or `npm install`), ensure you are in the `assets/` directory.
- **Backend Development**: Backend code is in the `src/` directory (FastAPI).
- **Type Checking**: Before finishing a task involving frontend changes, run `npx tsc --noEmit` in the `assets/` directory to ensure no regressions.

## Technology Stack
- **Frontend**: React, Tailwind CSS, Recharts, Lucide Icons.
- **Backend**: FastAPI, Pydantic v2.
- **Deployment**: GCP Cloud Run (Backend), Firebase Hosting (Frontend).

## Design Philosophy
- **Voyant-Style Visuals**: Prioritize stacked bar charts for cashflow. Use red bars (`deficit`) to indicate cashflow shortfalls clearly.
- **Interactive Planning**: Ensure the X-axis always shows the primary member's age clearly, with secondary members' ages listed beneath it.
- **UI Structure**: Maintain the layout of global parameters at the top, primary analysis in the middle (tabs for Charts/Breakdown), and asset/income data entry at the bottom.
