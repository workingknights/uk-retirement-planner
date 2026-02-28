# UK Retirement Planner

A modern, full-stack web application designed to help individuals in the UK visualize and plan their retirement. The application uses a Python/FastAPI backend for robust financial simulation and a React/Vite/Tailwind frontend for a dynamic, interactive user experience.

![Retirement Planner Screenshot](https://raw.githubusercontent.com/workingknights/uk-retirement-planner/main/frontend/public/vite.svg) *// Replace with actual screenshot*

## Features

- **Dynamic Visualization:** Interactive stacked area charts powered by Recharts illustrate asset balances and income streams over your entire lifetime.
- **Complex Asset Modeling:** Support for various asset types including Cash, General Investment Accounts (GIA), Stocks & Shares ISAs, Pensions, Property, and Company RSUs.
- **Flexible Income Streams:** Model specific income sources like the UK State Pension and Defined Benefit (DB) Pensions with defined start and end ages.
- **Intelligent Drawdown:** The simulation engine automatically prioritizes tax-efficient drawdowns (Cash -> GIA -> ISA -> Pension) when generated income falls short of your required retirement income.
- **Scenario Management:** Save your simulation parameters (inflation rates, retirement age, asset balances, etc.) as "Scenarios" and hot-swap between them seamlessly.
- **Color Synchronization:** Assets and their corresponding drawdowns are color-coded consistently across all charts for intuitive analysis.

## Tech Stack

**Frontend:**
- React 18
- Vite
- TypeScript
- Tailwind CSS
- Recharts (Data Visualization)
- Lucide React (Icons)

**Backend:**
- Python 3.x
- FastAPI
- Pydantic (Data Validation)
- Uvicorn
- Pytest (Unit Testing)

## Getting Started

### Prerequisites

- Node.js (v18+ recommended)
- Python (v3.10+ recommended)

### Backend Setup

1. Navigate to the `backend` directory:
   ```bash
   cd backend
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Start the FastAPI server:
   ```bash
   uvicorn main:app --reload
   ```
   The API will be available at `http://localhost:8000`.

### Frontend Setup

1. Open a new terminal and navigate to the `frontend` directory:
   ```bash
   cd frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Start the Vite development server:
   ```bash
   npm run dev
   ```
   The application will be available at `http://localhost:5173`.

## Testing

The backend includes a comprehensive suite of unit tests for the financial simulation engine. To run the tests:

```bash
cd backend
python -m pytest test_engine.py -v
```

## Contributing

Contributions are welcome! If you have suggestions or improvements, please open an issue or submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
