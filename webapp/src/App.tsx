import { useEffect, useState } from 'react'
import {
  Bell, ChevronLeft, CircleUserRound, Home, LockKeyhole, PieChart, Plus,
  ReceiptText, Settings, ShieldCheck, Sparkles, Users, WalletCards, Zap
} from 'lucide-react'
import { api, ensureUser, Expense, Group, Member, User } from './api'
import { haptic, telegramUser } from './telegram'

type Tab = 'home' | 'groups' | 'expense' | 'reports' | 'profile'
type GroupView = 'overview' | 'members' | 'settlements' | 'reports' | 'expense'

const categoryLabels: Record<string, string> = {
  food: '🍽 خورد و خوراک', transport: '🚕 رفت‌وآمد', stay: '🏨 اقامت', shopping: '🛍 خرید', entertainment: '🎉 تفریح', fuel: '⛽ سوخت', other: '📦 سایر'
}

const money = (value: string | number | undefined) => Number(value || 0).toLocaleString('fa-IR')
const isLocalDemo = () => ['localhost', '127.0.0.1'].includes(window.location.hostname) && !window.Telegram?.WebApp?.initData

export default function App() {
  const [user, setUser] = useState<User | null>(null)
  const [groups, setGroups] = useState<Group[]>([])
  const [tab, setTab] = useState<Tab>('home')
  const [selectedGroup, setSelectedGroup] = useState<Group | null>(null)
  const [groupView, setGroupView] = useState<GroupView>('overview')
  const [members, setMembers] = useState<Member[]>([])
  const [expenses, setExpenses] = useState<Expense[]>([])
  const [report, setReport] = useState<any>(null)
  const [debts, setDebts] = useState<any>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [showGuest, setShowGuest] = useState(false)

  useEffect(() => {
    ;(async () => {
      try {
        const me = await ensureUser()
        setUser(me)
        const list = await api.groups(me.id)
        setGroups(list)
        setShowGuest(!list.length)
      } catch (e) {
        if (isLocalDemo()) setShowGuest(true)
        else setError(e instanceof Error ? e.message : 'خطا در اتصال به دنگی دونگی')
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  async function openGroup(group: Group) {
    if (!user) return
    haptic()
    setSelectedGroup(group)
    setGroupView('overview')
    const [m, e, r, d] = await Promise.all([
      api.members(group.id), api.expenses(group.id), api.expenseReport(group.id, user.id), api.debtReport(group.id, user.id)
    ])
    setMembers(m); setExpenses(e); setReport(r); setDebts(d)
  }

  if (loading) return <div className="center-screen warm-bg"><div className="loader"/><p>در حال آماده‌سازی دنگی دونگی…</p></div>
  if (error) return <div className="center-screen error-card warm-bg"><b>اتصال برقرار نشد</b><p>{error}</p><small>Mini App را داخل Telegram باز کن و از فعال بودن API مطمئن شو.</small></div>
  if (showGuest) return <GuestLanding onExplore={() => setShowGuest(false)} hasDemo={isLocalDemo()} />

  if (selectedGroup) {
    return <GroupShell group={selectedGroup} view={groupView} onView={setGroupView} onBack={() => setSelectedGroup(null)}>
      {groupView === 'overview' && <GroupOverview members={members} expenses={expenses} report={report} debts={debts} onView={setGroupView}/>} 
      {groupView === 'members' && <MembersView members={members}/>} 
      {groupView === 'settlements' && <SettlementsView debts={debts}/>} 
      {groupView === 'reports' && <ReportsView report={report}/>} 
      {groupView === 'expense' && user && <ExpenseForm group={selectedGroup} user={user} members={members} onSaved={async()=>{setExpenses(await api.expenses(selectedGroup.id)); setGroupView('overview')}}/>}
    </GroupShell>
  }

  return <div className="app-shell warm-bg"><main className="screen">
    {tab === 'home' && <HomeView user={user!} groups={groups} onOpen={openGroup}/>} 
    {tab === 'groups' && <GroupsView groups={groups} onOpen={openGroup}/>} 
    {tab === 'expense' && <QuickExpense groups={groups} onOpen={(g)=>{openGroup(g).then(()=>setGroupView('expense'))}}/>}
    {tab === 'reports' && <GlobalReports groups={groups}/>} 
    {tab === 'profile' && <ProfileView user={user!}/>} 
  </main><BottomNav tab={tab} onChange={setTab}/></div>
}

function GuestLanding({onExplore,hasDemo}:{onExplore:()=>void;hasDemo:boolean}){
  const [step,setStep]=useState(1)
  return <div className="guest-page warm-bg"><main className="guest-shell">
    <section className="guest-hero soft-card">
      <div className="guest-badge"><Sparkles size={16}/> بدون ثبت‌نام امتحانش کنید</div>
      <div className="brand-orb"><Users/></div>
      <h1>دنگی دونگی</h1>
      <p>مدیریت هزینه‌های گروهی، ساده، شفاف و بدون تنش</p>
      <div className="people-illustration"><span>👩🏻</span><span>👨🏻</span><span>👩🏽</span><span>👨🏽</span></div>
    </section>

    <section className="soft-card intro-card"><h2>چرا دنگی دونگی؟</h2><div className="feature-grid">
      <Feature icon={<ReceiptText/>} title="ثبت سریع" text="هزینه‌ها را در چند ثانیه ثبت کن" tone="coral"/>
      <Feature icon={<Users/>} title="تقسیم عادلانه" text="سهم هر نفر را دقیق محاسبه کن" tone="gold"/>
      <Feature icon={<PieChart/>} title="گزارش هوشمند" text="همیشه تصویر روشنی از خرج‌ها داشته باش" tone="violet"/>
      <Feature icon={<WalletCards/>} title="تسویه آسان" text="بدهی‌ها را بدون سردرگمی ببند" tone="pink"/>
    </div></section>

    <section className="soft-card checklist-card"><div className="section-head"><h3>شروع در ۳ مرحله ساده</h3><span>{step}/3</span></div><div className="steps">
      {[['۱','ایجاد حساب'],['۲','دعوت اعضا'],['۳','ثبت هزینه‌ها']].map((x,i)=><button key={x[0]} className={`step-item ${step===i+1?'active':''} ${step>i+1?'done':''}`} onClick={()=>setStep(i+1)}><span>{step>i+1?'✓':x[0]}</span><b>{x[1]}</b></button>)}
    </div><div className="progress-track"><i style={{width:`${step/3*100}%`}}/></div></section>

    <section className="demo-panel soft-card"><div><small>دموی تعاملی</small><h3>قبل از شروع، خودت تجربه‌اش کن</h3><p>یک حساب نمونه با هزینه، اعضا، گزارش و تسویه آماده است.</p></div><button className="secondary-neu" onClick={onExplore}>شروع دمو</button></section>

    <section className="cta-stack"><button className="primary-neu"><Plus/> ایجاد حساب رایگان</button><button className="secondary-neu">ورود به حساب</button>{hasDemo&&<button className="text-btn" onClick={onExplore}>ادامه بدون ثبت‌نام (دمو)</button>}</section>

    <section className="trust-row"><div><Zap/><span>سریع</span></div><div><ShieldCheck/><span>امن</span></div><div><LockKeyhole/><span>خصوصی</span></div></section>
  </main></div>
}

function Feature({icon,title,text,tone}:{icon:any;title:string;text:string;tone:string}){return <div className="feature-item"><span className={`feature-icon ${tone}`}>{icon}</span><b>{title}</b><small>{text}</small></div>}

function Header({title, back}:{title:string;back?:()=>void}){
  const tgUser = telegramUser()
  return <header className="topbar"><button className="icon-btn soft-icon">{back ? <ChevronLeft onClick={back}/> : <Bell/>}</button><h1>{title}</h1><div className="avatar soft-avatar">{tgUser?.photo_url ? <img src={tgUser.photo_url}/> : (tgUser?.first_name?.[0] || 'د')}</div></header>
}

function HomeView({user,groups,onOpen}:{user:User;groups:Group[];onOpen:(g:Group)=>void}){
  return <><Header title="خانه"/><section className="hero-balance warm-gradient"><span>وضعیت کلی شما</span><strong>۲,۴۵۰,۰۰۰ تومان</strong><p>طلبکار هستید</p><WalletCards size={34}/></section><SectionTitle title="حساب‌های من" action="مشاهده همه"/><div className="stack">{groups.slice(0,3).map((g,i)=><button key={g.id} className="group-card soft-card" onClick={()=>onOpen(g)}><div className={`group-cover cover-${i%3}`}><span>{i===0?'🏖️':i===1?'🏠':'🎉'}</span></div><div><b>{g.raw_name || g.name}</b><small>{g.role === 'owner' ? '👑 مالک' : '👤 عضو'}</small><em>برای دیدن هزینه‌ها وارد شو</em></div><ChevronLeft/></button>)}</div><button className="primary-neu wide"><Plus/> حساب جدید</button></>
}

function GroupsView({groups,onOpen}:{groups:Group[];onOpen:(g:Group)=>void}){return <><Header title="حساب‌ها"/><div className="stack">{groups.map((g,i)=><button key={g.id} className="group-card soft-card" onClick={()=>onOpen(g)}><div className={`group-cover cover-${i%3}`}><span>{i%2?'🏠':'🌴'}</span></div><div><b>{g.raw_name||g.name}</b><small>{g.role === 'owner'?'مالک حساب':'عضو حساب'}</small></div><ChevronLeft/></button>)}</div><button className="primary-neu wide"><Plus/> ساخت حساب جدید</button></>}

function GroupShell({group,view,onView,onBack,children}:{group:Group;view:GroupView;onView:(v:GroupView)=>void;onBack:()=>void;children:any}){return <div className="app-shell warm-bg"><main className="screen"><Header title={group.raw_name||group.name} back={onBack}/>{children}</main><nav className="bottom-nav soft-nav"><NavItem active={view==='overview'} icon={<Home/>} label="خانه" onClick={()=>onView('overview')}/><NavItem active={view==='members'} icon={<Users/>} label="اعضا" onClick={()=>onView('members')}/><button className="fab warm-gradient" onClick={()=>onView('expense')}><Plus/></button><NavItem active={view==='reports'} icon={<PieChart/>} label="گزارش" onClick={()=>onView('reports')}/><NavItem active={view==='settlements'} icon={<WalletCards/>} label="تسویه" onClick={()=>onView('settlements')}/></nav></div>}

function GroupOverview({members,expenses,report,debts,onView}:{members:Member[];expenses:Expense[];report:any;debts:any;onView:(v:GroupView)=>void}){
  const total = report?.total_amount || 0
  return <><section className="group-hero soft-card"><div><span>{members.length} نفر</span><strong>{money(total)} تومان</strong><small>کل هزینه‌ها</small></div><div className="hero-photo">🏝️</div></section><button className="primary-neu wide" onClick={()=>onView('expense')}><Plus/> ثبت هزینه جدید</button><div className="action-grid"><Action icon={<ReceiptText/>} text="هزینه‌ها"/><Action icon={<WalletCards/>} text="تسویه‌ها" onClick={()=>onView('settlements')}/><Action icon={<Users/>} text="اعضا" onClick={()=>onView('members')}/><Action icon={<PieChart/>} text="گزارش‌ها" onClick={()=>onView('reports')}/><Action icon={<Settings/>} text="دسته‌بندی‌ها"/><Action icon={<Users/>} text="دعوت عضو"/></div><SectionTitle title="آخرین هزینه‌ها" action="مشاهده همه"/><div className="stack">{expenses.slice(0,5).map(x=><div className="expense-row soft-card" key={x.id}><div className="expense-icon">{categoryLabels[x.category||'other']?.split(' ')[0]||'🧾'}</div><div><b>{x.title}</b><small>{categoryLabels[x.category||'other'] || x.category || 'سایر'}</small></div><strong>{money(x.amount)}<small> تومان</small></strong></div>)}</div>{debts?.transfers?.length===0&&<div className="success-note soft-card">✅ این حساب در وضعیت تسویه است.</div>}</>
}

function MembersView({members}:{members:Member[]}){return <><div className="panel-title">اعضا</div><div className="list-card soft-card">{members.map(m=><div className="member-row" key={m.user_id}><div className="avatar mini soft-avatar">{m.display_name[0]}</div><b>{m.display_name}</b><span>{m.role==='owner'?'👑 مالک':m.role==='admin'?'🛡 مدیر':'عضو'}</span></div>)}</div><button className="primary-neu wide"><Plus/> دعوت عضو جدید</button></>}

function SettlementsView({debts}:{debts:any}){const transfers=debts?.transfers||[];return <><div className="segmented soft-card"><button className="active">بدهکاران</button><button>طلبکاران</button></div>{transfers.length===0?<div className="success-note soft-card">شما در این حساب تسویه هستید ✅</div>:<div className="stack">{transfers.map((x:any,i:number)=><div className="debt-card soft-card" key={i}><div><b>{x.from_name} → {x.to_name}</b><small>{money(x.amount)} تومان</small></div><button className="soft action-pill">تسویه</button></div>)}</div>}</>}

function ReportsView({report}:{report:any}){const cats=report?.categories||[];const total=Number(report?.total_amount||0);return <><div className="segmented soft-card"><button className="active">هزینه‌ها</button><button>بدهی‌ها</button></div><section className="report-summary soft-card"><span>کل هزینه‌ها</span><strong>{money(total)} تومان</strong></section><div className="report-card soft-card"><h3>هزینه‌ها بر اساس دسته‌بندی</h3><div className="donut"/><div className="legend">{cats.slice(0,6).map((c:any)=><div key={c.category}><span>{categoryLabels[c.category]||c.category}</span><b>{total?Math.round(Number(c.amount)/total*100):0}٪</b></div>)}</div></div></>}

function ExpenseForm({group,user,members,onSaved}:{group:Group;user:User;members:Member[];onSaved:()=>void}){
  const [title,setTitle]=useState(''); const [amount,setAmount]=useState(''); const [payer,setPayer]=useState(user.id); const [category,setCategory]=useState('food'); const [selected,setSelected]=useState<number[]>(members.map(m=>m.user_id)); const [busy,setBusy]=useState(false)
  async function submit(){if(!title||!amount||!selected.length)return;setBusy(true);try{await api.createExpense(group.id,{actor_user_id:user.id,paid_by_user_id:payer,amount,title,participant_user_ids:selected,split_mode:'equal',split_values:null,category});haptic();onSaved()}finally{setBusy(false)}}
  return <div className="form-card soft-card"><label>عنوان هزینه<input value={title} onChange={e=>setTitle(e.target.value)} placeholder="مثلاً شام رستوران"/></label><label>مبلغ (تومان)<input inputMode="numeric" value={amount} onChange={e=>setAmount(e.target.value.replace(/\D/g,''))} placeholder="1,850,000"/></label><label>پرداخت‌کننده<select value={payer} onChange={e=>setPayer(Number(e.target.value))}>{members.map(m=><option value={m.user_id} key={m.user_id}>{m.display_name}</option>)}</select></label><label>دسته‌بندی<select value={category} onChange={e=>setCategory(e.target.value)}>{Object.entries(categoryLabels).map(([k,v])=><option value={k} key={k}>{v}</option>)}</select></label><div className="field-label">بین چه کسانی تقسیم شود؟</div>{members.map(m=><label className="check-row" key={m.user_id}><input type="checkbox" checked={selected.includes(m.user_id)} onChange={()=>setSelected(s=>s.includes(m.user_id)?s.filter(x=>x!==m.user_id):[...s,m.user_id])}/><span>{m.display_name}</span></label>)}<div className="split-grid"><button className="active">⚖️ مساوی</button><button>٪ درصدی</button><button>💵 مبلغ مشخص</button></div><button className="primary-neu wide" disabled={busy} onClick={submit}>{busy?'در حال ثبت…':'ثبت هزینه'}</button></div>
}

function QuickExpense({groups,onOpen}:{groups:Group[];onOpen:(g:Group)=>void}){return <><Header title="ثبت هزینه"/><p className="muted">حساب موردنظر را انتخاب کن.</p><div className="stack">{groups.map(g=><button className="group-card simple soft-card" key={g.id} onClick={()=>onOpen(g)}><b>{g.raw_name||g.name}</b><ChevronLeft/></button>)}</div></>}
function GlobalReports({groups}:{groups:Group[]}){return <><Header title="گزارش‌ها"/><div className="empty-state soft-card"><PieChart size={52}/><b>گزارش هر حساب در صفحه همان حساب قرار دارد</b><p>یکی از {groups.length} حساب خودت را باز کن تا نمودار هزینه‌ها و وضعیت بدهی‌ها را ببینی.</p></div></>}
function ProfileView({user}:{user:User}){const tgUser=telegramUser();return <><Header title="پروفایل من"/><div className="profile-head"><div className="avatar xl soft-avatar">{tgUser?.photo_url?<img src={tgUser.photo_url}/>:user.display_name[0]}</div><h2>{user.display_name}</h2><small>{tgUser?.username?`@${tgUser.username}`:'حساب تلگرام'}</small></div><div className="list-card settings-list soft-card"><button>💳 اطلاعات کارت بانکی <ChevronLeft/></button><button>🔐 امنیت و ورود <ChevronLeft/></button><button>🔔 اعلان‌ها <ChevronLeft/></button><button>🎧 پشتیبانی <ChevronLeft/></button></div></>}

function BottomNav({tab,onChange}:{tab:Tab;onChange:(t:Tab)=>void}){return <nav className="bottom-nav soft-nav"><NavItem active={tab==='home'} icon={<Home/>} label="خانه" onClick={()=>onChange('home')}/><NavItem active={tab==='groups'} icon={<ReceiptText/>} label="حساب‌ها" onClick={()=>onChange('groups')}/><button className="fab warm-gradient" onClick={()=>onChange('expense')}><Plus/></button><NavItem active={tab==='reports'} icon={<PieChart/>} label="گزارش" onClick={()=>onChange('reports')}/><NavItem active={tab==='profile'} icon={<CircleUserRound/>} label="پروفایل" onClick={()=>onChange('profile')}/></nav>}
function NavItem({active,icon,label,onClick}:{active:boolean;icon:any;label:string;onClick:()=>void}){return <button className={`nav-item ${active?'active':''}`} onClick={onClick}>{icon}<span>{label}</span></button>}
function Action({icon,text,onClick}:{icon:any;text:string;onClick?:()=>void}){return <button className="action soft-card" onClick={onClick}>{icon}<span>{text}</span></button>}
function SectionTitle({title,action}:{title:string;action:string}){return <div className="section-title"><b>{title}</b><span>{action}</span></div>}
