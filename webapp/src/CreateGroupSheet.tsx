import { useState } from 'react'
import { Plus, X } from 'lucide-react'

export default function CreateGroupSheet({onClose,onCreate}:{onClose:()=>void;onCreate:(name:string)=>Promise<void>}){
  const [name,setName]=useState('')
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState('')

  async function submit(){
    const clean=name.trim()
    if(!clean){setError('اسم حساب را وارد کن.');return}
    setBusy(true);setError('')
    try{await onCreate(clean)}catch(e){setError(e instanceof Error?e.message:'ساخت حساب انجام نشد');setBusy(false)}
  }

  return <div className="sheet-backdrop" role="dialog" aria-modal="true">
    <section className="create-sheet soft-card">
      <div className="sheet-handle"/>
      <div className="sheet-head"><div><small>قدم اول</small><h2>حساب جدید بساز</h2></div><button className="sheet-close" onClick={onClose}><X/></button></div>
      <p className="sheet-copy">یک اسم ساده انتخاب کن؛ مثلاً «سفر شمال»، «خانه» یا «تولد سارا».</p>
      <label className="sheet-field">نام حساب<input autoFocus maxLength={120} value={name} onChange={e=>setName(e.target.value)} onKeyDown={e=>{if(e.key==='Enter')submit()}} placeholder="مثلاً سفر شمال 🌴"/></label>
      <div className="sheet-hint"><span>💡</span><p>بعد از ساخت، می‌تونی اعضا را دعوت کنی و اولین هزینه را ثبت کنی.</p></div>
      {error&&<div className="sheet-error">{error}</div>}
      <button className="primary-neu wide" disabled={busy} onClick={submit}><Plus/>{busy?'در حال ساخت…':'ساخت حساب'}</button>
      <button className="text-btn" onClick={onClose}>فعلاً نه</button>
    </section>
  </div>
}
