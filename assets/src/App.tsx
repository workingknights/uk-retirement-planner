import { useEffect, useState } from 'react'
import { Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, AreaChart, Area, ReferenceLine, LineChart } from 'recharts'
import { Plus, Trash2, TrendingUp, Save, Download, X, ChevronDown, ChevronUp, PanelLeftClose, PanelLeftOpen, LogIn, UserCircle, LogOut } from 'lucide-react'
import React from 'react'
import { API_BASE_URL } from './config'

// Firebase Imports
import { initializeApp } from "firebase/app";
import { getAuth, signInWithPopup, GoogleAuthProvider, onAuthStateChanged, signOut } from "firebase/auth";

// Firebase configuration using environment variables
const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID
};

// Initialize Firebase
const firebaseApp = initializeApp(firebaseConfig);
const firebaseAuth = getAuth(firebaseApp);
const googleProvider = new GoogleAuthProvider();


interface AuthState {
  checked: boolean        // has the /api/me fetch completed?
  authenticated: boolean
  email: string | null
  local: boolean          // true when running without Cloudflare Access configured
}

// Basic types
type AssetType = 'isa' | 'pension' | 'general' | 'cash' | 'property' | 'rsu' | 'premium_bonds'
type IncomeSourceType = 'state_pension' | 'db_pension' | 'employment' | 'other'
type WithdrawalStrategy = 'sequential' | 'blended'

interface BlendedStrategyParams {
  isa_drawdown_pct: number
  pension_drawdown_pct: number
  isa_topup_from_pension: number
}

interface Person {
  id: string
  name: string
}

interface AssetOwnership {
  person_id: string
  share: number // 0.0 to 1.0
}

interface LifeEvent {
  id: string
  name: string
  age: number
}

interface Asset {
  id: string
  name: string
  type: AssetType
  balance: number
  annual_growth_rate: number
  annual_contribution: number
  is_withdrawable: boolean
  max_annual_withdrawal: number | null
  owners: AssetOwnership[]
  dividend_yield: number | null
}

interface IncomeSource {
  id: string
  name: string
  type: IncomeSourceType
  amount: number
  start_age: number
  end_age: number
  person_id: string | null
}

interface SimulationParams {
  current_age: number
  retirement_age: number
  life_expectancy: number
  inflation_rate: number
  desired_annual_income: number
  people: Person[]
  assets: Asset[]
  incomes: IncomeSource[]
  life_events: LifeEvent[]
  withdrawal_priority: AssetType[]
  withdrawal_strategy: WithdrawalStrategy
  blended_params: BlendedStrategyParams | null
}

interface WhatIfScenario {
  id: string
  name: string
  inflationOffset: number // e.g. +1.0 for 1% higher inflation
  growthOffset: number // e.g. -1.0 for 1% lower asset growth
}

const defaultParams: SimulationParams = {
  current_age: 40,
  retirement_age: 60,
  life_expectancy: 90,
  inflation_rate: 2.5,
  desired_annual_income: 40000,
  people: [
    { id: 'p1', name: 'Person 1' }
  ],
  assets: [
    { id: '1', name: 'Workplace Pension', type: 'pension', balance: 150000, annual_growth_rate: 6.0, annual_contribution: 6000, is_withdrawable: true, max_annual_withdrawal: null, owners: [{ person_id: 'p1', share: 1.0 }], dividend_yield: null },
    { id: '2', name: 'S&S ISA', type: 'isa', balance: 50000, annual_growth_rate: 5.0, annual_contribution: 10000, is_withdrawable: true, max_annual_withdrawal: null, owners: [{ person_id: 'p1', share: 1.0 }], dividend_yield: null },
    { id: '3', name: 'Primary Residence', type: 'property', balance: 350000, annual_growth_rate: 3.0, annual_contribution: 0, is_withdrawable: false, max_annual_withdrawal: null, owners: [{ person_id: 'p1', share: 1.0 }], dividend_yield: null }
  ],
  incomes: [
    { id: '1', name: 'State Pension', type: 'state_pension', amount: 10600, start_age: 68, end_age: 100, person_id: 'p1' },
    { id: '2', name: 'Final Salary Scheme', type: 'db_pension', amount: 15000, start_age: 60, end_age: 100, person_id: 'p1' }
  ],
  life_events: [
    { id: '1', name: 'Retirement (P1)', age: 60 },
    { id: '2', name: 'Downsize Home', age: 75 }
  ],
  withdrawal_priority: ['cash', 'premium_bonds', 'general', 'rsu', 'isa', 'pension'],
  withdrawal_strategy: 'sequential',
  blended_params: null,
}

function App() {
  const [params, setParams] = useState<SimulationParams>(defaultParams)
  const [whatIfs, setWhatIfs] = useState<WhatIfScenario[]>([])

  const [simulationData, setSimulationData] = useState<any>(null)
  const [whatIfData, setWhatIfData] = useState<Record<string, any[]>>({})
  const [loading, setLoading] = useState(false)
  const [assetsExpanded, setAssetsExpanded] = useState(false)
  const [incomesExpanded, setIncomesExpanded] = useState(false)
  const [eventsExpanded, setEventsExpanded] = useState(false)
  const [whatIfsExpanded, setWhatIfsExpanded] = useState(false)
  const [sidebarVisible, setSidebarVisible] = useState(true)
  const [topRowExpanded, setTopRowExpanded] = useState(true)

  const [auth, setAuth] = useState<AuthState>({ checked: false, authenticated: false, email: null, local: true })

  const [scenarios, setScenarios] = useState<{ id: string, name: string, last_modified?: number }[]>([])
  const [showLoadModal, setShowLoadModal] = useState(false)
  const [showSaveModal, setShowSaveModal] = useState(false)
  const [saveName, setSaveName] = useState('')
  const [currentScenarioName, setCurrentScenarioName] = useState('')

  // Whether save/load should be available to this user
  const scenariosEnabled = auth.local || auth.authenticated

  // Wrapper for all Worker API calls — sends token explicitly for GCP Firebase Auth
  const apiFetch = async (url: string, options: RequestInit = {}) => {
    const user = firebaseAuth.currentUser;
    const headers = new Headers(options.headers || {});
    if (user) {
      const token = await user.getIdToken();
      headers.set('Authorization', `Bearer ${token}`);
    }
    // Use standard fetch without redirect hacks, as Firebase Auth bypasses the cross-origin login redirects.
    return fetch(url, { ...options, headers });
  }

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(firebaseAuth, (user) => {
      if (user) {
        setAuth({ checked: true, authenticated: true, email: user.email, local: false });
      } else {
        setAuth({ checked: true, authenticated: false, email: null, local: false });
      }
    });

    return () => unsubscribe();
  }, [])

  const handleSignIn = async (e: React.MouseEvent) => {
    e.preventDefault();
    try {
      await signInWithPopup(firebaseAuth, googleProvider);
    } catch (error) {
      console.error("Login failed", error);
    }
  };

  const handleSignOut = async () => {
    try {
      await signOut(firebaseAuth);
    } catch (error) {
      console.error("Logout failed", error);
    }
  };

  useEffect(() => {
    if (scenariosEnabled) fetchScenarios()
  }, [scenariosEnabled])

  const [confirmOverwrite, setConfirmOverwrite] = useState(false)

  const processSave = async () => {
    try {
      const existing = scenarios.find(s => s.name.toLowerCase() === saveName.trim().toLowerCase());
      if (existing && confirmOverwrite) {
        await apiFetch(`${API_BASE_URL}/api/scenarios/${existing.id}`, { method: 'DELETE' });
      }

      const res = await apiFetch(`${API_BASE_URL}/api/scenarios`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: saveName.trim(), data: params })
      })
      
      const data = await res.json()
      if (data.success && data.data && data.data.id) {
        // Optimistic UI update to bypass Cloudflare KV list() eventual consistency (~60s delay)
        let nextScenarios = scenarios;
        if (existing && confirmOverwrite) {
          nextScenarios = nextScenarios.filter(s => s.id !== existing.id);
        }
        nextScenarios = [...nextScenarios, { id: data.data.id, name: saveName.trim(), last_modified: Math.floor(Date.now() / 1000) }];
        setScenarios(nextScenarios);
      }

      setShowSaveModal(false)
      setConfirmOverwrite(false)
      setCurrentScenarioName(saveName.trim())
      setSaveName('')
      
      // Still fetch just in case, but rely on optimistic state primarily
      fetchScenarios()
    } catch (e) { console.error('Failed to save scenario', e) }
  }

  const handleSaveScenario = async () => {
    if (!saveName.trim()) return

    if (!confirmOverwrite) {
      const existing = scenarios.find(s => s.name.toLowerCase() === saveName.trim().toLowerCase());
      if (existing) {
        setConfirmOverwrite(true)
        return;
      }
    }
    
    await processSave()
  }

  const handleOpenSaveModal = () => {
    setSaveName(currentScenarioName)
    setShowSaveModal(true)
  }

  const handleLoadScenario = async (id: string) => {
    try {
      const res = await apiFetch(`${API_BASE_URL}/api/scenarios/${id}`)
      const data = await res.json()
      if (data.success) {
        // Robust backward-compatible merge with defaultParams
        const loadedParams = { ...defaultParams, ...data.data.data }
        setParams(loadedParams)
        setCurrentScenarioName(data.data.name)
        setShowLoadModal(false)
        setSimulationData(null) // clear previous sim
      }
    } catch (e) { console.error('Failed to load scenario', e) }
  }

  const handleDeleteScenario = async (id: string) => {
    try {
      await apiFetch(`${API_BASE_URL}/api/scenarios/${id}`, { method: 'DELETE' })
      fetchScenarios()
    } catch (e) { console.error('Failed to delete scenario', e) }
  }

  const handleSimulate = async () => {
    setLoading(true)
    try {
      // 1. Fetch base scenario
      const baseResponse = await apiFetch(`${API_BASE_URL}/api/simulate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params)
      })
      const baseData = await baseResponse.json()
      if (baseData.success) {
        setSimulationData(baseData.data.timeline)
      }

      // 2. Fetch what-if scenarios concurrently
      if (whatIfs.length > 0) {
        const whatIfPromises = whatIfs.map(async (scenario) => {
          // Create modified params for this scenario
          const scenarioParams: SimulationParams = {
            ...params,
            inflation_rate: Number((Number(params.inflation_rate) + Number(scenario.inflationOffset)).toFixed(2)),
            assets: params.assets.map(a => ({
              ...a,
              annual_growth_rate: Number((Number(a.annual_growth_rate) + Number(scenario.growthOffset)).toFixed(2))
            }))
          }

          const response = await apiFetch(`${API_BASE_URL}/api/simulate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(scenarioParams)
          })
          const data = await response.json()
          return { id: scenario.id, timeline: data.success ? data.data.timeline : null }
        })

        const whatIfResults = await Promise.all(whatIfPromises)
        const newWhatIfData: Record<string, any[]> = {}
        whatIfResults.forEach(res => {
          if (res.timeline) {
            newWhatIfData[res.id] = res.timeline
          }
        })
        setWhatIfData(newWhatIfData)
      } else {
        setWhatIfData({}) // clear if none
      }

    } catch (error) {
      console.error('Failed to simulate', error)
    } finally {
      setLoading(false)
    }
  }

  // Consistent color generation based on index for assets and incomes
  const getAssetColor = (index: number) => {
    const hue = (index * 137.5) % 360;
    return `hsl(${hue}, 70%, 50%)`;
  }

  const getIncomeColor = (name: string) => {
    // If it's an asset withdrawal, match the asset's color
    if (name.startsWith('Withdrawal: ')) {
      const assetName = name.replace('Withdrawal: ', '');
      const assetIndex = params.assets.findIndex(a => a.name === assetName);
      if (assetIndex !== -1) return getAssetColor(assetIndex);
    }

    // Otherwise, generate a distinct color for the standalone income source
    const incomeIndex = params.incomes.findIndex(i => i.name === name);
    const hue = ((incomeIndex + params.assets.length) * 137.5) % 360;
    return `hsl(${hue}, 60%, 45%)`;
  }

  const updateParam = (field: keyof SimulationParams, value: any) => {
    setParams(prev => ({ ...prev, [field]: value }))
  }

  const handleAddAsset = () => {
    const newAsset: Asset = {
      id: Math.random().toString(),
      name: 'New Asset',
      type: 'isa',
      balance: 0,
      annual_growth_rate: 5.0,
      annual_contribution: 0,
      is_withdrawable: true,
      max_annual_withdrawal: null,
      owners: [],
      dividend_yield: null,
    }
    setParams(prev => ({ ...prev, assets: [...prev.assets, newAsset] }))
  }

  const handleUpdateAsset = (id: string, field: keyof Asset, value: any) => {
    setParams(prev => ({
      ...prev,
      assets: prev.assets.map(a => a.id === id ? { ...a, [field]: value } : a)
    }))
  }

  const handleRemoveAsset = (id: string) => {
    setParams(prev => ({ ...prev, assets: prev.assets.filter(a => a.id !== id) }))
  }

  const handleAddIncome = () => {
    const newIncome: IncomeSource = {
      id: Math.random().toString(),
      name: 'New Income',
      type: 'other',
      amount: 0,
      start_age: 60,
      end_age: 100,
      person_id: params.people.length > 0 ? params.people[0].id : null,
    }
    setParams(prev => ({ ...prev, incomes: [...prev.incomes, newIncome] }))
  }

  const handleUpdateIncome = (id: string, field: keyof IncomeSource, value: any) => {
    setParams(prev => ({
      ...prev,
      incomes: prev.incomes.map(i => i.id === id ? { ...i, [field]: value } : i)
    }))
  }

  const handleRemoveIncome = (id: string) => {
    setParams(prev => ({ ...prev, incomes: prev.incomes.filter(i => i.id !== id) }))
  }

  const handleAddLifeEvent = () => {
    const newEvent: LifeEvent = {
      id: Math.random().toString(),
      name: 'New Event',
      age: 65,
    }
    setParams(prev => ({ ...prev, life_events: [...prev.life_events, newEvent] }))
  }

  const handleUpdateLifeEvent = (id: string, field: keyof LifeEvent, value: any) => {
    setParams(prev => ({
      ...prev,
      life_events: prev.life_events.map(e => e.id === id ? { ...e, [field]: value } : e)
    }))
  }

  const handleRemoveLifeEvent = (id: string) => {
    setParams(prev => ({ ...prev, life_events: prev.life_events.filter(e => e.id !== id) }))
  }

  const handleAddWhatIf = () => {
    // Max 3 scenarios for performance/UI clarity
    if (whatIfs.length >= 3) return;
    const newWhatIf: WhatIfScenario = {
      id: Math.random().toString(),
      name: `Scenario ${String.fromCharCode(65 + whatIfs.length)}`, // A, B, C...
      inflationOffset: 0,
      growthOffset: 0,
    }
    setWhatIfs(prev => [...prev, newWhatIf])
  }

  const handleUpdateWhatIf = (id: string, field: keyof WhatIfScenario, value: any) => {
    setWhatIfs(prev => prev.map(s => s.id === id ? { ...s, [field]: value } : s))
  }

  const handleRemoveWhatIf = (id: string) => {
    setWhatIfs(prev => prev.filter(s => s.id !== id))
  }

  const fetchScenarios = async () => {
    try {
      const res = await apiFetch(`${API_BASE_URL}/api/scenarios`)
      const data = await res.json()
      if (data.success) setScenarios(data.data)
    } catch (e) { console.error('Failed to fetch scenarios', e) }
  }

  useEffect(() => {
    if (scenariosEnabled) fetchScenarios()
  }, [scenariosEnabled])


  return (
    <div className="min-h-screen p-8 max-w-7xl mx-auto space-y-8">

      {/* Auth banner — shown in prod when not yet authenticated */}
      {auth.checked && !auth.local && !auth.authenticated && (
        <div className="flex items-center justify-between bg-amber-50 border border-amber-200 rounded-xl px-5 py-3 text-sm text-amber-800">
          <span>Sign in to save and load scenarios across sessions.</span>
          <button
            onClick={handleSignIn}
            className="flex items-center space-x-1.5 font-semibold text-amber-900 hover:text-amber-700 transition-colors"
          >
            <LogIn size={16} />
            <span>Sign In</span>
          </button>
        </div>
      )}

      <header className="flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <button
            onClick={() => setSidebarVisible(!sidebarVisible)}
            title={sidebarVisible ? "Hide Sidebar" : "Show Sidebar"}
            className="flex items-center justify-center bg-white hover:bg-slate-50 text-slate-700 border border-slate-200 p-2.5 rounded-xl shadow-sm transition-all"
          >
            {sidebarVisible ? <PanelLeftClose size={20} /> : <PanelLeftOpen size={20} />}
          </button>
          <div>
            <h1 className="text-3xl font-bold bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent">
              UK Retirement Planner
            </h1>
            <p className="text-slate-500 mt-1 hidden sm:block">Plan your future with confidence and clarity.</p>
          </div>
        </div>
        <div className="flex items-center space-x-3">
          {/* User badge — shown when authenticated */}
          {auth.authenticated && auth.email && (
            <div className="flex items-center space-x-3 text-sm">
              <div className="flex items-center space-x-1.5 text-slate-600 bg-slate-100 border border-slate-200 rounded-xl px-3 py-2">
                <UserCircle size={16} className="text-indigo-500" />
                <span className="hidden sm:inline max-w-[160px] truncate">{auth.email}</span>
              </div>
              <button 
                onClick={handleSignOut}
                title="Sign Out"
                className="p-2 text-slate-400 hover:text-rose-500 transition-colors"
              >
                <LogOut size={20} />
              </button>
            </div>
          )}

          <button
            onClick={() => scenariosEnabled ? setShowLoadModal(true) : undefined}
            disabled={!scenariosEnabled}
            title={!scenariosEnabled ? 'Sign in to load scenarios' : 'Load a saved scenario'}
            className="flex items-center space-x-2 bg-white hover:bg-slate-50 text-slate-700 border border-slate-200 px-4 py-2.5 rounded-xl font-medium shadow-sm transition-all disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Download size={18} />
            <span className="hidden sm:inline">Load</span>
          </button>
          <button
            onClick={scenariosEnabled ? handleOpenSaveModal : undefined}
            disabled={!scenariosEnabled}
            title={!scenariosEnabled ? 'Sign in to save scenarios' : 'Save current scenario'}
            className="flex items-center space-x-2 bg-white hover:bg-slate-50 text-slate-700 border border-slate-200 px-4 py-2.5 rounded-xl font-medium shadow-sm transition-all disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Save size={18} />
            <span>Save</span>
          </button>
          <button
            onClick={handleSimulate}
            disabled={loading}
            className="flex items-center space-x-2 bg-indigo-600 hover:bg-indigo-700 text-white px-6 py-2.5 rounded-xl font-medium shadow-lg shadow-indigo-200 transition-all disabled:opacity-50"
          >
            <TrendingUp size={20} />
            <span>{loading ? 'Calculating...' : 'Run Simulation'}</span>
          </button>
        </div>
      </header>

      {/* Top Row: Household & Parameters */}
      <div className="bg-slate-50 rounded-2xl border border-slate-200 overflow-hidden">
        <div 
          className="flex justify-between items-center p-4 cursor-pointer hover:bg-slate-100 transition-colors"
          onClick={() => setTopRowExpanded(!topRowExpanded)}
        >
          <div className="flex items-center space-x-2">
            {topRowExpanded ? <ChevronUp size={20} className="text-slate-500" /> : <ChevronDown size={20} className="text-slate-500" />}
            <h2 className="text-lg font-semibold text-slate-800">Household & Parameters</h2>
          </div>
          <span className="text-xs text-slate-400 hidden sm:inline">
            {params.people.length} People, {params.retirement_age} Retirement, £{params.desired_annual_income.toLocaleString()} Target
          </span>
        </div>
        
        {topRowExpanded && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8 p-6 pt-2 border-t border-slate-200/60">
            <section className="space-y-4">
              <div className="flex justify-between items-center">
                <h3 className="text-sm font-semibold text-slate-600 uppercase tracking-wider">Household Members</h3>
            <button onClick={() => {
              const newPerson: Person = { id: Math.random().toString(36), name: 'New Person' }
              setParams(prev => ({ ...prev, people: [...prev.people, newPerson] }))
            }} className="text-indigo-600 hover:text-indigo-800"><Plus size={20} /></button>
          </div>
          <div className="space-y-3">
            {params.people.map(person => (
              <div key={person.id} className="flex items-center space-x-2">
                <input
                  value={person.name}
                  onChange={e => setParams(prev => ({ ...prev, people: prev.people.map(p => p.id === person.id ? { ...p, name: e.target.value } : p) }))}
                  className="flex-1 rounded-md border-slate-300 shadow-sm p-2 border text-sm"
                />
                <button onClick={() => setParams(prev => ({ ...prev, people: prev.people.filter(p => p.id !== person.id) }))} className="text-slate-400 hover:text-red-500">
                  <Trash2 size={16} />
                </button>
              </div>
            ))}
            {params.people.length === 0 && <p className="text-xs text-slate-400">Add people to enable tax modelling.</p>}
          </div>
            </section>

            <section className="space-y-4">
              <h3 className="text-sm font-semibold text-slate-600 uppercase tracking-wider">Parameters</h3>
              <div className="grid grid-cols-2 gap-4">
            <label className="block text-sm font-medium text-slate-700">
              Current Age
              <input type="number" value={params.current_age} onChange={e => updateParam('current_age', Number(e.target.value))} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 p-2 border" />
            </label>
            <label className="block text-sm font-medium text-slate-700">
              Retirement Age
              <input type="number" value={params.retirement_age} onChange={e => updateParam('retirement_age', Number(e.target.value))} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 p-2 border" />
            </label>
            <label className="block text-sm font-medium text-slate-700">
              Desired Annual Income (Today's Value)
              <input type="number" value={params.desired_annual_income} onChange={e => updateParam('desired_annual_income', Number(e.target.value))} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 p-2 border" />
            </label>
            <label className="block text-sm font-medium text-slate-700">
              Inflation Rate (%)
              <input type="number" step="0.1" value={params.inflation_rate} onChange={e => updateParam('inflation_rate', Number(e.target.value))} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 p-2 border" />
            </label>
            <label className="block text-sm font-medium text-slate-700 col-span-2">
              Withdrawal Strategy
              <select value={params.withdrawal_strategy} onChange={e => {
                const strategy = e.target.value as WithdrawalStrategy;
                updateParam('withdrawal_strategy', strategy);
                if (strategy === 'blended' && !params.blended_params) {
                  updateParam('blended_params', { isa_drawdown_pct: 4.0, pension_drawdown_pct: 5.0, isa_topup_from_pension: 20000 });
                }
              }} className="mt-1 block w-full rounded-md border-slate-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 p-2 border">
                <option value="sequential">Sequential (Priority Order)</option>
                <option value="blended">Blended Tax-Optimised</option>
              </select>
            </label>
          </div>
          {params.withdrawal_strategy === 'blended' && params.blended_params && (
            <div className="mt-3 p-3 bg-indigo-50 rounded-lg border border-indigo-200 space-y-2">
              <p className="text-xs text-indigo-600 font-semibold">Blended Strategy Settings</p>
              <div className="grid grid-cols-3 gap-3">
                <label className="block text-xs text-slate-600">
                  ISA Drawdown (%)
                  <input type="number" step="0.5" value={params.blended_params.isa_drawdown_pct} onChange={e => updateParam('blended_params', { ...params.blended_params!, isa_drawdown_pct: Number(e.target.value) })} className="mt-1 block w-full rounded border-slate-300 p-1.5 border text-sm" />
                </label>
                <label className="block text-xs text-slate-600">
                  Pension Drawdown (%)
                  <input type="number" step="0.5" value={params.blended_params.pension_drawdown_pct} onChange={e => updateParam('blended_params', { ...params.blended_params!, pension_drawdown_pct: Number(e.target.value) })} className="mt-1 block w-full rounded border-slate-300 p-1.5 border text-sm" />
                </label>
                <label className="block text-xs text-slate-600">
                  ISA Top-up (£/yr)
                  <input type="number" step="1000" value={params.blended_params.isa_topup_from_pension} onChange={e => updateParam('blended_params', { ...params.blended_params!, isa_topup_from_pension: Number(e.target.value) })} className="mt-1 block w-full rounded border-slate-300 p-1.5 border text-sm" />
                </label>
              </div>
              <p className="text-[10px] text-indigo-400 italic">From Apr 2027 pensions are subject to IHT — recycling into ISA is more tax-efficient</p>
            </div>
              )}
            </section>
          </div>
        )}
      </div>

      <div className={`grid grid-cols-1 gap-8 ${sidebarVisible ? 'lg:grid-cols-4' : 'lg:grid-cols-1'}`}>
        {sidebarVisible && (
          <div className="space-y-6 lg:col-span-1 pr-4 lg:border-r border-slate-200">

            <section className="space-y-4">
              <div className="flex justify-between items-center cursor-pointer hover:bg-slate-50 p-2 -mx-2 rounded-lg transition-colors" onClick={() => setAssetsExpanded(!assetsExpanded)}>
                <div className="flex items-center space-x-2">
                  {assetsExpanded ? <ChevronUp size={20} className="text-slate-500" /> : <ChevronDown size={20} className="text-slate-500" />}
                  <h2 className="text-xl font-semibold text-slate-800">Assets ({params.assets.length})</h2>
                </div>
                <button onClick={(e) => { e.stopPropagation(); handleAddAsset(); }} className="text-indigo-600 hover:text-indigo-800 p-1">
                  <Plus size={20} />
                </button>
              </div>
              {assetsExpanded && params.assets.map(asset => (
                <div key={asset.id} className="bg-white p-4 rounded-xl shadow-sm border border-slate-200 space-y-3 relative group">
                  <button onClick={() => handleRemoveAsset(asset.id)} className="absolute top-4 right-4 text-slate-400 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity">
                    <Trash2 size={16} />
                  </button>
                  <input value={asset.name} onChange={e => handleUpdateAsset(asset.id, 'name', e.target.value)} className="font-semibold text-slate-800 bg-transparent border-none p-0 focus:ring-0 w-full" />
                  <div className="grid grid-cols-2 gap-3">
                    <label className="block text-xs text-slate-500">
                      Type
                      <select value={asset.type} onChange={e => {
                        handleUpdateAsset(asset.id, 'type', e.target.value as AssetType);
                        if (e.target.value === 'property') handleUpdateAsset(asset.id, 'is_withdrawable', false);
                      }} className="mt-1 block w-full rounded border-slate-300 p-1.5 border text-sm">
                        <option value="pension">Pension</option>
                        <option value="isa">ISA</option>
                        <option value="premium_bonds">Premium Bonds</option>
                        <option value="general">GIA</option>
                        <option value="cash">Cash</option>
                        <option value="property">Property</option>
                        <option value="rsu">Company RSUs</option>
                      </select>
                    </label>
                    <label className="block text-xs text-slate-500">
                      Balance (£)
                      <input type="number" value={asset.balance} onChange={e => handleUpdateAsset(asset.id, 'balance', Number(e.target.value))} className="mt-1 block w-full rounded border-slate-300 p-1.5 border text-sm" />
                    </label>
                    <label className="block text-xs text-slate-500">
                      Growth (%)
                      <input type="number" step="0.1" value={asset.annual_growth_rate} onChange={e => handleUpdateAsset(asset.id, 'annual_growth_rate', Number(e.target.value))} className="mt-1 block w-full rounded border-slate-300 p-1.5 border text-sm" />
                    </label>
                    <label className="block text-xs text-slate-500">
                      Contrib. (£/yr)
                      <input type="number" value={asset.annual_contribution} onChange={e => handleUpdateAsset(asset.id, 'annual_contribution', Number(e.target.value))} className="mt-1 block w-full rounded border-slate-300 p-1.5 border text-sm" />
                    </label>
                    <label className="flex items-center space-x-2 text-xs text-slate-500 col-span-2 mt-2">
                      <input type="checkbox" checked={asset.is_withdrawable} onChange={e => handleUpdateAsset(asset.id, 'is_withdrawable', e.target.checked)} className="rounded border-slate-300" />
                      <span>Use to fund retirement income</span>
                    </label>
                    {asset.is_withdrawable && (
                      <label className="block text-xs text-slate-500 col-span-2">
                        Max Annual Withdrawal (£, optional CGT cap)
                        <input
                          type="number"
                          placeholder="No limit"
                          value={asset.max_annual_withdrawal ?? ''}
                          onChange={e => handleUpdateAsset(asset.id, 'max_annual_withdrawal', e.target.value === '' ? null : Number(e.target.value))}
                          className="mt-1 block w-full rounded border-slate-300 p-1.5 border text-sm"
                        />
                      </label>
                    )}
                    {asset.type === 'general' && (
                      <label className="block text-xs text-slate-500 col-span-2">
                        Dividend Yield (% of balance, taxable annually)
                        <input
                          type="number"
                          step="0.1"
                          placeholder="e.g. 3.5"
                          value={asset.dividend_yield ?? ''}
                          onChange={e => handleUpdateAsset(asset.id, 'dividend_yield', e.target.value === '' ? null : Number(e.target.value))}
                          className="mt-1 block w-full rounded border-slate-300 p-1.5 border text-sm"
                        />
                      </label>
                    )}
                    {params.people.length > 0 && (
                      <div className="col-span-2 mt-1 space-y-1">
                        <p className="text-xs font-medium text-slate-500">Ownership</p>
                        {params.people.map(person => {
                          const own = asset.owners.find(o => o.person_id === person.id)
                          return (
                            <div key={person.id} className="flex items-center space-x-2">
                              <span className="text-xs text-slate-600 w-24 truncate">{person.name}</span>
                              <input
                                type="number" min="0" max="100" step="1"
                                placeholder="0"
                                value={own ? Math.round(own.share * 100) : ''}
                                onChange={e => {
                                  const pct = e.target.value === '' ? 0 : Number(e.target.value) / 100
                                  const updated = asset.owners.filter(o => o.person_id !== person.id)
                                  if (pct > 0) updated.push({ person_id: person.id, share: pct })
                                  handleUpdateAsset(asset.id, 'owners', updated)
                                }}
                                className="w-16 rounded border-slate-300 p-1 border text-sm"
                              />
                              <span className="text-xs text-slate-400">%</span>
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </section>

            <section className="space-y-4 pt-6 border-t border-slate-200">
              <div className="flex justify-between items-center cursor-pointer hover:bg-slate-50 p-2 -mx-2 rounded-lg transition-colors" onClick={() => setIncomesExpanded(!incomesExpanded)}>
                <div className="flex items-center space-x-2">
                  {incomesExpanded ? <ChevronUp size={20} className="text-slate-500" /> : <ChevronDown size={20} className="text-slate-500" />}
                  <h2 className="text-xl font-semibold text-slate-800">Income Sources ({params.incomes.length})</h2>
                </div>
                <button onClick={(e) => { e.stopPropagation(); handleAddIncome(); }} className="text-indigo-600 hover:text-indigo-800 p-1">
                  <Plus size={20} />
                </button>
              </div>
              {incomesExpanded && params.incomes.map(income => (
                <div key={income.id} className="bg-white p-4 rounded-xl shadow-sm border border-slate-200 space-y-3 relative group">
                  <button onClick={() => handleRemoveIncome(income.id)} className="absolute top-4 right-4 text-slate-400 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity">
                    <Trash2 size={16} />
                  </button>
                  <input value={income.name} onChange={e => handleUpdateIncome(income.id, 'name', e.target.value)} className="font-semibold text-slate-800 bg-transparent border-none p-0 focus:ring-0 w-full" />
                  <div className="grid grid-cols-2 gap-3">
                    <label className="block text-xs text-slate-500">
                      Type
                      <select value={income.type} onChange={e => handleUpdateIncome(income.id, 'type', e.target.value as IncomeSourceType)} className="mt-1 block w-full rounded border-slate-300 p-1.5 border text-sm">
                        <option value="state_pension">State Pension</option>
                        <option value="db_pension">DB Pension</option>
                        <option value="employment">Employment</option>
                        <option value="other">Other</option>
                      </select>
                    </label>
                    <label className="block text-xs text-slate-500">
                      Amount (£/yr)
                      <input type="number" value={income.amount} onChange={e => handleUpdateIncome(income.id, 'amount', Number(e.target.value))} className="mt-1 block w-full rounded border-slate-300 p-1.5 border text-sm" />
                    </label>
                    <label className="block text-xs text-slate-500">
                      Start Age
                      <input type="number" value={income.start_age} onChange={e => handleUpdateIncome(income.id, 'start_age', Number(e.target.value))} className="mt-1 block w-full rounded border-slate-300 p-1.5 border text-sm" />
                    </label>
                    <label className="block text-xs text-slate-500">
                      End Age
                      <input type="number" value={income.end_age} onChange={e => handleUpdateIncome(income.id, 'end_age', Number(e.target.value))} className="mt-1 block w-full rounded border-slate-300 p-1.5 border text-sm" />
                    </label>
                    {params.people.length > 0 && (
                      <label className="block text-xs text-slate-500 col-span-2">
                        Owner
                        <select
                          value={income.person_id ?? ''}
                          onChange={e => handleUpdateIncome(income.id, 'person_id', e.target.value || null)}
                          className="mt-1 block w-full rounded border-slate-300 p-1.5 border text-sm"
                        >
                          <option value="">Unassigned</option>
                          {params.people.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                        </select>
                      </label>
                    )}
                  </div>
                </div>
              ))}
            </section>

            <section className="space-y-4 pt-6 border-t border-slate-200">
              <div className="flex justify-between items-center cursor-pointer hover:bg-slate-50 p-2 -mx-2 rounded-lg transition-colors" onClick={() => setEventsExpanded(!eventsExpanded)}>
                <div className="flex items-center space-x-2">
                  {eventsExpanded ? <ChevronUp size={20} className="text-slate-500" /> : <ChevronDown size={20} className="text-slate-500" />}
                  <h2 className="text-xl font-semibold text-slate-800">Life Events ({params.life_events.length})</h2>
                </div>
                <button onClick={(e) => { e.stopPropagation(); handleAddLifeEvent(); }} className="text-indigo-600 hover:text-indigo-800 p-1">
                  <Plus size={20} />
                </button>
              </div>
              {eventsExpanded && params.life_events.map(evt => (
                <div key={evt.id} className="bg-white p-4 rounded-xl shadow-sm border border-slate-200 space-y-3 relative group">
                  <button onClick={() => handleRemoveLifeEvent(evt.id)} className="absolute top-4 right-4 text-slate-400 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity">
                    <Trash2 size={16} />
                  </button>
                  <input value={evt.name} onChange={e => handleUpdateLifeEvent(evt.id, 'name', e.target.value)} className="font-semibold text-slate-800 bg-transparent border-none p-0 focus:ring-0 w-full" placeholder="Event Name" />
                  <div className="grid grid-cols-1 gap-3">
                    <label className="block text-xs text-slate-500">
                      Age it occurs
                      <input type="number" value={evt.age} onChange={e => handleUpdateLifeEvent(evt.id, 'age', Number(e.target.value))} className="mt-1 block w-full rounded border-slate-300 p-1.5 border text-sm" />
                    </label>
                  </div>
                </div>
              ))}
            </section>

            <section className="space-y-4 pt-6 border-t border-slate-200">
              <div className="flex justify-between items-center cursor-pointer hover:bg-slate-50 p-2 -mx-2 rounded-lg transition-colors" onClick={() => setWhatIfsExpanded(!whatIfsExpanded)}>
                <div className="flex items-center space-x-2">
                  {whatIfsExpanded ? <ChevronUp size={20} className="text-slate-500" /> : <ChevronDown size={20} className="text-slate-500" />}
                  <h2 className="text-xl font-semibold text-slate-800">What-If Scenarios ({whatIfs.length})</h2>
                </div>
                <button onClick={(e) => { e.stopPropagation(); handleAddWhatIf(); }} disabled={whatIfs.length >= 3} className="disabled:text-slate-300 text-indigo-600 hover:text-indigo-800 transition-colors p-1">
                  <Plus size={20} />
                </button>
              </div>
              {whatIfsExpanded && whatIfs.length === 0 && (
                <p className="text-sm text-slate-500 italic px-2">Add a scenario to compare against the base plan.</p>
              )}
              {whatIfsExpanded && whatIfs.map(scenario => (
                <div key={scenario.id} className="bg-slate-50 p-4 rounded-xl shadow-sm border border-slate-300 space-y-3 relative group">
                  <button onClick={() => handleRemoveWhatIf(scenario.id)} className="absolute top-4 right-4 text-slate-400 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity">
                    <Trash2 size={16} />
                  </button>
                  <input value={scenario.name} onChange={e => handleUpdateWhatIf(scenario.id, 'name', e.target.value)} className="font-semibold text-slate-800 bg-transparent border-none p-0 focus:ring-0 w-full" placeholder="Scenario Name" />
                  <div className="grid grid-cols-2 gap-3">
                    <label className="block text-xs text-slate-500">
                      Inflation Offset (%)
                      <input type="number" step="0.1" value={scenario.inflationOffset} onChange={e => handleUpdateWhatIf(scenario.id, 'inflationOffset', Number(e.target.value))} className="mt-1 block w-full rounded border-slate-300 p-1.5 border text-sm" />
                    </label>
                    <label className="block text-xs text-slate-500">
                      Asset Growth Offset (%)
                      <input type="number" step="0.1" value={scenario.growthOffset} onChange={e => handleUpdateWhatIf(scenario.id, 'growthOffset', Number(e.target.value))} className="mt-1 block w-full rounded border-slate-300 p-1.5 border text-sm" />
                    </label>
                  </div>
                </div>
              ))}
            </section>
          </div>
        )}

        <div className={`${sidebarVisible ? 'lg:col-span-3' : 'lg:col-span-4'} space-y-8`}>
          {!simulationData ? (
            <div className="bg-slate-100 rounded-2xl h-96 flex flex-col items-center justify-center text-slate-500 border-2 border-dashed border-slate-300">
              <TrendingUp size={48} className="mb-4 text-slate-400" />
              <p>Configure parameters and run simulation to see projection</p>
            </div>
          ) : (
            <>
              <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                <h3 className="text-lg font-semibold text-slate-800 mb-6">Asset Balances Over Time</h3>
                <div className="h-80">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={simulationData}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                      <XAxis dataKey="age" tick={{ fill: '#64748b' }} tickLine={false} />
                      <YAxis tickFormatter={(val: number) => `£${(val / 1000).toFixed(0)}k`} width={80} tick={{ fill: '#64748b' }} tickLine={false} axisLine={false} />
                      <Tooltip formatter={(value: any) => `£${Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`} />
                      <Legend />
                      {params.assets.map((asset, index) => {
                        const color = getAssetColor(index);
                        return (
                          <Area key={asset.name} type="monotone" dataKey={`asset_balances.${asset.name}`} name={asset.name} stackId="1" stroke={color} fill={color} fillOpacity={0.6} />
                        )
                      })}
                      {params.life_events.map(evt => (
                        <ReferenceLine key={evt.id} x={evt.age} stroke="#94a3b8" strokeDasharray="3 3">
                          <text x={evt.age} y={20} fill="#64748b" fontSize={11} textAnchor="start" dx={5}>{evt.name}</text>
                        </ReferenceLine>
                      ))}
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </div>

              <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                <h3 className="text-lg font-semibold text-slate-800 mb-6">Income & Withdrawals</h3>
                <div className="h-80">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={simulationData}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                      <XAxis dataKey="age" tick={{ fill: '#64748b' }} tickLine={false} />
                      <YAxis tickFormatter={(val: number) => `£${(val / 1000).toFixed(0)}k`} width={80} tick={{ fill: '#64748b' }} tickLine={false} axisLine={false} />
                      <Tooltip formatter={(value: any) => `£${Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`} />
                      <Legend />

                      {/* Dynamically map income components from all simulation years */}
                      {(() => {
                        if (!simulationData) return null;
                        const keys = new Set<string>();
                        simulationData.forEach((year: any) => {
                          Object.keys(year.income_breakdown).forEach(k => keys.add(k));
                        });
                        return Array.from(keys).map((incomeKey) => {
                          const color = getIncomeColor(incomeKey);
                          return (
                            <Area key={incomeKey} type="monotone" dataKey={`income_breakdown.${incomeKey}`} name={incomeKey} stackId="1" stroke={color} fill={color} fillOpacity={0.6} />
                          )
                        });
                      })()}

                      <Line type="step" dataKey="required_income" stroke="#ef4444" strokeWidth={2} strokeDasharray="5 5" name="Required Income" dot={false} />
                      {params.life_events.map(evt => (
                        <ReferenceLine key={evt.id} x={evt.age} stroke="#94a3b8" strokeDasharray="3 3">
                          <text x={evt.age} y={20} fill="#64748b" fontSize={11} textAnchor="start" dx={5}>{evt.name}</text>
                        </ReferenceLine>
                      ))}
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {params.people.length > 0 && (() => {
                const taxData = simulationData.map((year: any) => {
                  const row: any = { age: year.age }
                  params.people.forEach(p => {
                    row[`tax_${p.name}`] = year.tax_breakdown?.[p.name]?.total ?? 0
                  })
                  return row
                })
                return (
                  <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                    <h3 className="text-lg font-semibold text-slate-800 mb-2">Estimated Tax Liability</h3>
                    <p className="text-xs text-slate-500 mb-4">Income Tax + CGT per person (2024/25 rates, simplified).</p>
                    <div className="h-72">
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={taxData} margin={{ top: 5, right: 20, left: 20, bottom: 5 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                          <XAxis dataKey="age" tick={{ fontSize: 12 }} />
                          <YAxis tickFormatter={(v: number) => `£${(v / 1000).toFixed(0)}k`} tick={{ fontSize: 12 }} />
                          <Tooltip formatter={(value: any) => `£${Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`} />
                          <Legend />
                          {params.people.map((p, idx) => {
                            const hue = (idx * 80 + 200) % 360
                            const color = `hsl(${hue}, 65%, 45%)`
                            return (
                              <Area key={p.id} type="monotone" dataKey={`tax_${p.name}`} name={`${p.name} Tax`} stackId="1" stroke={color} fill={color} fillOpacity={0.6} />
                            )
                          })}
                          {params.life_events.map(evt => (
                            <ReferenceLine key={evt.id} x={evt.age} stroke="#94a3b8" strokeDasharray="3 3">
                              <text x={evt.age} y={20} fill="#64748b" fontSize={11} textAnchor="start" dx={5}>{evt.name}</text>
                            </ReferenceLine>
                          ))}
                        </AreaChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                )
              })()}

              {/* Combined Scenarios Chart */}
              {whatIfs.length > 0 && Object.keys(whatIfData).length > 0 && (() => {
                // Build combined data array
                const combinedData = simulationData.map((baseYear: any, index: number) => {
                  const row: any = { age: baseYear.age, Base: baseYear.total_assets }
                  whatIfs.forEach(scenario => {
                    const scenarioTimeline = whatIfData[scenario.id]
                    if (scenarioTimeline && scenarioTimeline[index]) {
                      row[scenario.name] = scenarioTimeline[index].total_assets
                    }
                  })
                  return row
                })

                const scenarioColors = ['#10b981', '#f59e0b', '#ec4899'] // Emerald, Amber, Pink

                return (
                  <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                    <h3 className="text-lg font-semibold text-slate-800 mb-2">Scenario Comparison (Total Assets)</h3>
                    <p className="text-xs text-slate-500 mb-4">Comparing the baseline projection with your what-if scenarios.</p>
                    <div className="h-72">
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={combinedData} margin={{ top: 5, right: 20, left: 20, bottom: 5 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
                          <XAxis dataKey="age" tick={{ fontSize: 12, fill: '#64748b' }} tickLine={false} />
                          <YAxis tickFormatter={(v: number) => `£${(v / 1000).toFixed(0)}k`} tick={{ fontSize: 12, fill: '#64748b' }} tickLine={false} axisLine={false} width={80} />
                          <Tooltip formatter={(value: any) => `£${Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`} />
                          <Legend />
                          <Line type="monotone" dataKey="Base" stroke="#3b82f6" strokeWidth={3} dot={false} />
                          {whatIfs.map((scenario, idx) => (
                            <Line key={scenario.id} type="monotone" dataKey={scenario.name} stroke={scenarioColors[idx % scenarioColors.length]} strokeWidth={2} strokeDasharray="5 5" dot={false} />
                          ))}
                          {params.life_events.map(evt => (
                            <ReferenceLine key={evt.id} x={evt.age} stroke="#94a3b8" strokeDasharray="3 3">
                              <text x={evt.age} y={20} fill="#64748b" fontSize={11} textAnchor="start" dx={5}>{evt.name}</text>
                            </ReferenceLine>
                          ))}
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                )
              })()}
            </>
          )}

          {/* Tabular View */}
          {simulationData && params.people.length > 0 && (() => {
            // Filter data to only show from 1 year prior to retirement
            const tableData = simulationData.filter((year: any) => year.age >= params.retirement_age - 1);
            
            // Collect possible income sources across the visible years for columns
            const allIncomeKeys = new Set<string>();
            tableData.forEach((year: any) => {
              Object.keys(year.income_breakdown).forEach(k => allIncomeKeys.add(k));
            });
            const incomeColumns = Array.from(allIncomeKeys);

            return (
              <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 mt-8">
                <h3 className="text-lg font-semibold text-slate-800 mb-4">Annual Breakdown (From Age {Math.max(params.current_age, params.retirement_age - 1)})</h3>
                <div className="overflow-x-auto rounded-xl border border-slate-200">
                  <table className="min-w-full text-sm text-left text-slate-600">
                    <thead className="text-xs text-slate-700 uppercase bg-slate-50 border-b border-slate-200">
                      <tr>
                        <th className="px-4 py-3 font-semibold">Age</th>
                        {incomeColumns.map(col => (
                          <React.Fragment key={col}>
                            <th className="px-4 py-3 font-semibold text-slate-700 bg-slate-100/50">{col} (Income)</th>
                            <th className="px-4 py-3 font-semibold text-rose-700/80 bg-rose-50/30">{col} (Tax)</th>
                          </React.Fragment>
                        ))}
                        <th className="px-4 py-3 font-semibold text-indigo-700 bg-indigo-50 border-x border-slate-200">Total Income</th>
                        {params.people.map(p => (
                          <th key={p.id} className="px-4 py-3 font-semibold">{p.name} Tax</th>
                        ))}
                        <th className="px-4 py-3 font-semibold text-rose-700 bg-rose-50 border-l border-slate-200">Total Tax</th>
                      </tr>
                    </thead>
                    <tbody>
                      {tableData.map((year: any) => {
                        const totalTax = params.people.reduce((sum, p) => sum + (year.tax_breakdown?.[p.name]?.total ?? 0), 0);
                        return (
                          <tr key={year.age} className="border-b border-slate-100 hover:bg-slate-50 transition-colors">
                            <td className="px-4 py-2 font-medium text-slate-900">{year.age}</td>
                            {incomeColumns.map(col => (
                              <React.Fragment key={col}>
                                <td className="px-4 py-2 font-medium text-slate-700 bg-slate-50/50">
                                  £{Number(year.income_breakdown[col] || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                                </td>
                                <td className="px-4 py-2 text-rose-600/80 bg-rose-50/30">
                                  £{Number(year.tax_by_source?.[col] || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                                </td>
                              </React.Fragment>
                            ))}
                            <td className="px-4 py-2 font-semibold text-indigo-700 bg-indigo-50/50 border-x border-slate-200">
                              £{Number(year.total_income || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                            </td>
                            {params.people.map(p => (
                              <td key={p.id} className="px-4 py-2">
                                £{Number(year.tax_breakdown?.[p.name]?.total || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                              </td>
                            ))}
                            <td className="px-4 py-2 font-semibold text-rose-700 bg-rose-50/50 border-l border-slate-200">
                              £{Number(totalTax || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )
          })()}

        </div>
      </div>

      {/* Save Modal */}
      {showSaveModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl p-6 w-full max-w-sm shadow-xl">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-semibold">Save Scenario</h3>
              <button onClick={() => setShowSaveModal(false)} className="text-slate-400 hover:text-slate-600"><X size={20} /></button>
            </div>
            <input
              autoFocus
              type="text"
              placeholder="e.g. Early Retirement"
              value={saveName}
              onChange={e => {
                setSaveName(e.target.value)
                setConfirmOverwrite(false)
              }}
              className="w-full p-2 border border-slate-300 rounded-lg mb-4"
              onKeyDown={e => e.key === 'Enter' && handleSaveScenario()}
            />
          <div className="flex justify-end space-x-3">
              <button 
                onClick={() => {
                  setShowSaveModal(false)
                  setConfirmOverwrite(false)
                }} 
                className="px-4 py-2 text-slate-600 hover:bg-slate-100 rounded-lg"
              >
                Cancel
              </button>
              <button 
                onClick={handleSaveScenario} 
                disabled={!saveName.trim()} 
                className={`px-4 py-2 text-white rounded-lg disabled:opacity-50 ${confirmOverwrite ? 'bg-red-600 hover:bg-red-700' : 'bg-indigo-600 hover:bg-indigo-700'}`}
              >
                {confirmOverwrite ? "Confirm Overwrite" : "Save"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Load Modal */}
      {showLoadModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl p-6 w-full max-w-md shadow-xl flex flex-col max-h-[80vh]">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-semibold">Load Scenario</h3>
              <button onClick={() => setShowLoadModal(false)} className="text-slate-400 hover:text-slate-600"><X size={20} /></button>
            </div>
            <div className="flex-1 overflow-y-auto space-y-2 min-h-[100px]">
              {scenarios.length === 0 ? (
                <p className="text-slate-500 text-center py-8">No saved scenarios yet.</p>
              ) : (
                scenarios.map(s => (
                  <div key={s.id} className="flex items-center justify-between p-3 border border-slate-200 rounded-lg hover:bg-slate-50 group">
                    <div className="flex-1 cursor-pointer" onClick={() => handleLoadScenario(s.id)}>
                      <div className="font-medium text-slate-700">{s.name}</div>
                      {s.last_modified && (
                        <div className="text-xs text-slate-500 mt-0.5">
                          {new Date(s.last_modified * 1000).toLocaleString('en-GB', {
                            day: 'numeric', month: 'short', year: 'numeric',
                            hour: '2-digit', minute: '2-digit'
                          })}
                        </div>
                      )}
                    </div>
                    <button onClick={() => handleDeleteScenario(s.id)} className="text-slate-400 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity p-2">
                      <Trash2 size={18} />
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default App
