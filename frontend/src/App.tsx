import { useEffect, useState } from 'react'
import { Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, AreaChart, Area } from 'recharts'
import { Plus, Trash2, TrendingUp, Save, Download, X } from 'lucide-react'

// Basic types
type AssetType = 'isa' | 'pension' | 'general' | 'cash' | 'property' | 'rsu' | 'premium_bonds'
type IncomeSourceType = 'state_pension' | 'db_pension' | 'employment' | 'other'

interface Person {
  id: string
  name: string
}

interface AssetOwnership {
  person_id: string
  share: number // 0.0 to 1.0
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
  withdrawal_priority: AssetType[]
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
    { id: '1', name: 'Workplace Pension', type: 'pension', balance: 150000, annual_growth_rate: 6.0, annual_contribution: 6000, is_withdrawable: true, max_annual_withdrawal: null, owners: [{ person_id: 'p1', share: 1.0 }] },
    { id: '2', name: 'S&S ISA', type: 'isa', balance: 50000, annual_growth_rate: 5.0, annual_contribution: 10000, is_withdrawable: true, max_annual_withdrawal: null, owners: [{ person_id: 'p1', share: 1.0 }] },
    { id: '3', name: 'Primary Residence', type: 'property', balance: 350000, annual_growth_rate: 3.0, annual_contribution: 0, is_withdrawable: false, max_annual_withdrawal: null, owners: [{ person_id: 'p1', share: 1.0 }] }
  ],
  incomes: [
    { id: '1', name: 'State Pension', type: 'state_pension', amount: 10600, start_age: 68, end_age: 100, person_id: 'p1' },
    { id: '2', name: 'Final Salary Scheme', type: 'db_pension', amount: 15000, start_age: 60, end_age: 100, person_id: 'p1' }
  ],
  withdrawal_priority: ['cash', 'premium_bonds', 'general', 'rsu', 'isa', 'pension']
}

function App() {
  const [params, setParams] = useState<SimulationParams>(defaultParams)
  const [simulationData, setSimulationData] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  const [scenarios, setScenarios] = useState<{ id: string, name: string, last_modified?: number }[]>([])
  const [showLoadModal, setShowLoadModal] = useState(false)
  const [showSaveModal, setShowSaveModal] = useState(false)
  const [saveName, setSaveName] = useState('')
  const [currentScenarioName, setCurrentScenarioName] = useState('')

  const fetchScenarios = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/scenarios')
      const data = await res.json()
      if (data.success) setScenarios(data.data)
    } catch (e) { console.error('Failed to fetch scenarios', e) }
  }

  useEffect(() => {
    fetchScenarios()
  }, [])

  const handleSaveScenario = async () => {
    if (!saveName.trim()) return

    // Check if name already exists
    const existing = scenarios.find(s => s.name.toLowerCase() === saveName.trim().toLowerCase());
    if (existing) {
      if (!window.confirm(`A scenario named "${saveName}" already exists. Do you want to overwrite it?`)) {
        return;
      }
    }

    try {
      await fetch('http://localhost:8000/api/scenarios', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: saveName.trim(), data: params })
      })
      setShowSaveModal(false)
      setCurrentScenarioName(saveName.trim())
      setSaveName('')
      fetchScenarios()
    } catch (e) { console.error('Failed to save scenario', e) }
  }

  const handleOpenSaveModal = () => {
    setSaveName(currentScenarioName)
    setShowSaveModal(true)
  }

  const handleLoadScenario = async (id: string) => {
    try {
      const res = await fetch(`http://localhost:8000/api/scenarios/${id}`)
      const data = await res.json()
      if (data.success) {
        setParams(data.data.data)
        setCurrentScenarioName(data.data.name)
        setShowLoadModal(false)
        setSimulationData(null) // clear previous sim
      }
    } catch (e) { console.error('Failed to load scenario', e) }
  }

  const handleDeleteScenario = async (id: string) => {
    try {
      await fetch(`http://localhost:8000/api/scenarios/${id}`, { method: 'DELETE' })
      fetchScenarios()
    } catch (e) { console.error('Failed to delete scenario', e) }
  }

  const handleSimulate = async () => {
    setLoading(true)
    try {
      const response = await fetch('http://localhost:8000/api/simulate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params)
      })
      const data = await response.json()
      if (data.success) {
        setSimulationData(data.data.timeline)
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

  return (
    <div className="min-h-screen p-8 max-w-7xl mx-auto space-y-8">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent">
            UK Retirement Planner
          </h1>
          <p className="text-slate-500 mt-1">Plan your future with confidence and clarity.</p>
        </div>
        <div className="flex space-x-3">
          <button
            onClick={() => setShowLoadModal(true)}
            className="flex items-center space-x-2 bg-white hover:bg-slate-50 text-slate-700 border border-slate-200 px-4 py-2.5 rounded-xl font-medium shadow-sm transition-all"
          >
            <Download size={18} />
            <span>Load</span>
          </button>
          <button
            onClick={handleOpenSaveModal}
            className="flex items-center space-x-2 bg-white hover:bg-slate-50 text-slate-700 border border-slate-200 px-4 py-2.5 rounded-xl font-medium shadow-sm transition-all"
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

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="space-y-6 lg:col-span-1 border-r border-slate-200 pr-8">

          <section className="space-y-4">
            <div className="flex justify-between items-center">
              <h2 className="text-xl font-semibold text-slate-800">Household</h2>
              <button onClick={() => {
                const newPerson: Person = { id: Math.random().toString(36), name: 'New Person' }
                setParams(prev => ({ ...prev, people: [...prev.people, newPerson] }))
              }} className="text-indigo-600 hover:text-indigo-800"><Plus size={20} /></button>
            </div>
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
          </section>

          <section className="space-y-4 pt-6 border-t border-slate-200">
            <h2 className="text-xl font-semibold text-slate-800">Parameters</h2>
            <div className="space-y-3">
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
            </div>
          </section>

          <section className="space-y-4 pt-6 border-t border-slate-200">
            <div className="flex justify-between items-center">
              <h2 className="text-xl font-semibold text-slate-800">Assets</h2>
              <button onClick={handleAddAsset} className="text-indigo-600 hover:text-indigo-800">
                <Plus size={20} />
              </button>
            </div>
            {params.assets.map(asset => (
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
            <div className="flex justify-between items-center">
              <h2 className="text-xl font-semibold text-slate-800">Income Sources</h2>
              <button onClick={handleAddIncome} className="text-indigo-600 hover:text-indigo-800">
                <Plus size={20} />
              </button>
            </div>
            {params.incomes.map(income => (
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
        </div>

        <div className="lg:col-span-2 space-y-8">
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
                        </AreaChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                )
              })()}
            </>
          )}
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
              onChange={e => setSaveName(e.target.value)}
              className="w-full p-2 border border-slate-300 rounded-lg mb-4"
              onKeyDown={e => e.key === 'Enter' && handleSaveScenario()}
            />
            <div className="flex justify-end space-x-3">
              <button onClick={() => setShowSaveModal(false)} className="px-4 py-2 text-slate-600 hover:bg-slate-100 rounded-lg">Cancel</button>
              <button onClick={handleSaveScenario} disabled={!saveName.trim()} className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50">Save</button>
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
