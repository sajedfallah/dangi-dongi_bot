import { useEffect, useMemo, useState } from 'react'
import {
  AlertCircle, Bell, Check, ChevronLeft, CircleUserRound, Copy, CreditCard, Home,
  LockKeyhole, PieChart, Plus, ReceiptText, Save, Settings, Share2, ShieldCheck,
  Sparkles, UserPlus, Users, WalletCards, X, Zap
} from 'lucide-react'
import {
  api, BOT_USERNAME, Expense, Group, GroupCategory, InvitePayload, Member,
  PaymentProfile, Settlement, User
} from './api'
import { ensureUser } from './api'
import { haptic, telegramUser } from './telegram'
import CreateGroupSheet from './CreateGroupSheet'

type Tab = 'home' | 'groups' | 'expense' | 'reports' | 'profile'
type GroupView = 'overview' | 'members' | 'settlements' | 'reports' | 'expense'
type SplitMode = 'equal' | 'percentage' | 'shares' | 'exact'

const categoryLabels: Record<string, string> = {
  food: '🍽 خورد و خوراک', transport: '🚕 رفت‌وآمد', stay: '🏨 اقامت', shopping: '🛍 خرید',
  entertainment: '🎉 تفریح', fuel: '⛽ سوخت', other: '📦 سایر'
}
const money = (value: string | number | undefined) => Number(value || 0).toLocaleString('fa-IR')
const isLocalDemo = () => ['localhost', '127.0.0.1'].includes(window.location.hostname) && !window.Telegram?.WebApp?.initData
const memberName = (members: Member[], userId: number) => members.find(m => m.user_id === userId)?.display_name || 'کاربر'

export default function App() {
  const [user, setUser] = useState<User | null>(null)
  const [groups, setGroups] = useState<Group[]>([])
  const [tab, setTab] = useState<Tab>('home')
  const [selectedGroup, setSelectedGroup] = useState<Group | null>(null)
  const [groupView, setGroupView] = useState<GroupView>('overview')
  const [members, setMembers] = useState<Member[]>([])
  const [expenses, setExpenses] = useState<Expense[]>([])
  const [categories, setCategories] = useState<GroupCategory[]>([])
  const [report, setReport] = useState<any>(null)
  const [debts, setDebts] = useState<any>(null)
  const [pending, setPending] = useState<Settlement[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [showGuest, setShowGuest] = useState(false)
  const [creatingGroup, setCreatingGroup] = useState(false)

  useEffect(() => {
    ;(async () => {
      try {
        const me = await ensureUser()
        setUser(me)
        const list = await api.groups(me.id)
        setGroups(list)
        setShowGuest(isLocalDemo() || !list.length)
      } catch (e) {
        if (isLocalDemo()) setShowGuest(true)
        else setError(e instanceof Error ? e.message : 'خطا در اتصال به دنگی دونگی')
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  async function refreshGroup(group = selectedGroup) {
    if (!user || !group) return
    const [m, e, c, r, d, p] = await Promise.all([
      api.members(group.id), api.expenses(group.id), api.categories(group.id, user.id),
      api.expenseReport(group.id, user.id), api.debtReport(group.id, user.id),
      api.pendingSettlements(group.id, user.id)
    ])
    setMembers(m); setExpenses(e); setCategories(c); setReport(r); setDebts(d); setPending(p)
  }

  async function openGroup(group: Group) {
    if (!user) return
    haptic()
    setSelectedGroup(group)
    setGroupView('overview')
    await refreshGroup(group)
  }

  async function createGroup(name: string) {
    if (!user) throw new Error('کاربر هنوز آماده نشده است.')
    const group = await api.createGroup(user.id, name)
    setGroups(await api.groups(user.id))
    setCreatingGroup(false)
    setShowGuest(false)
    await openGroup(group)
  }

  const startCreate = () => { setShowGuest(false); setCreatingGroup(true); haptic() }
  const enterDemo = () => { setShowGuest(false); setTab('home'); haptic() }

  if (loading) return <div className="center-screen warm-bg"><div className="loader"/><p>در حال آماده‌سازی دنگی دونگی…</p></div>
  if (error) return <div className="center-screen error-card warm-bg"><b>اتصال برقرار نشد</b><p>{error}</p><small>Mini App را داخل Telegram باز کن و از فعال بودن API مطمئن شو.</small></div>
  if (showGuest) return <GuestLanding onExplore={enterDemo} onCreate={startCreate} hasDemo={isLocalDemo()} />

  if (selectedGroup && user) {
    return <>
      <GroupShell group={selectedGroup} view={groupView} onView={setGroupView} onBack={() => setSelectedGroup(null)}>
        {groupView === 'overview' && <GroupOverview members={members} expenses={expenses} report={report} debts={debts} onView={setGroupView}/>} 
        {groupView === 'members' && <MembersView group={selectedGroup} user={user} members={members}/>} 
        {groupView === 'settlements' && <SettlementsView group={selectedGroup} user={user} members={members} debts={debts} pending={pending} onRefresh={() => refreshGroup(selectedGroup)}/>} 
        {groupView === 'reports' && <ReportsView report={report} debts={debts}/>} 
        {groupView === 'expense' && <ExpenseForm group={selectedGroup} user={user} members={members} categories={categories} onSaved={async () => { await refreshGroup(selectedGroup); setGroupView('overview') }}/>} 
      </GroupShell>
      {creatingGroup && <CreateGroupSheet onClose={() => setCreatingGroup(false)} onCreate={createGroup}/>} 
    </>
  }

  return <div className="app-shell warm-bg"><main className="screen">
    {tab === 'home' && <HomeView user={user!} groups={groups} onOpen={openGroup} onCreate={startCreate}/>} 
    {tab === 'groups' && <GroupsView groups={groups} onOpen={openGroup} onCreate={startCreate}/>} 
    {tab === 'expense' && <QuickExpense groups={groups} onOpen={(g) => { openGroup(g).then(() => setGroupView('expense')) }} onCreate={startCreate}/>} 
    {tab === 'reports' && <GlobalReports groups={groups} onOpen={openGroup}/>} 
    {tab === 'profile' && user && <ProfileView user={user}/>} 
  </main><BottomNav tab={tab} onChange={setTab}/>{creatingGroup && <CreateGroupSheet onClose={() => setCreatingGroup(false)} onCreate={createGroup}/>}</div>
}

function GuestLanding({onExplore,onCreate,hasDemo}:{onExplore:()=>void;onCreate:()=>void;hasDemo:boolean}){
  const [step,setStep]=useState(1)
  return <div className="guest-page warm-bg"><main className="guest-shell">
    <section className="guest-hero soft-card">
      <div className="guest-badge"><Sparkles size={16}/> بدون ثبت‌نام امتحانش کنید</div>
      <div className="brand-orb"><Users/></div>
      <h1>دنگی دونگی</h1>
      <p>مدیریت هزینه‌های گروهی، ساده، شفاف و بدون تنش</p>
      <div className="people-illustration"/>
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
    <section className="demo-panel soft-card"><div><small>دموی تعاملی</small><h3>قبل از شروع، خودت تجربه‌اش کن</h3><p>یک حساب نمونه با هزینه، اعضا، گزارش و تسویه آماده است.</p></div><button className="secondary-neu" onClick={onExplore}>مشاهده دمو</button></section>
    <section className="cta-stack"><button className="primary-neu" onClick={onCreate}><Plus/> ایجاد حساب رایگان</button><button className="secondary-neu" onClick={onExplore}>ورود به حساب</button>{hasDemo&&<button className="text-btn" onClick={onExplore}>ادامه بدون ثبت‌نام (دمو)</button>}</section>
    <section className="trust-row"><div><Zap/><span>سریع</span></div><div><ShieldCheck/><span>امن</span></div><div><LockKeyhole/><span>خصوصی</span></div></section>
  </main></div>
}

function Feature({icon,title,text,tone}:{icon:any;title:string;text:string;tone:string}){return <div className="feature-item"><span className={`feature-icon ${tone}`}>{icon}</span><b>{title}</b><small>{text}</small></div>}

function Header({title, back}:{title:string;back?:()=>void}){
  const tgUser = telegramUser()
  return <header className="topbar"><button className="icon-btn soft-icon" onClick={back}>{back ? <ChevronLeft/> : <Bell/>}</button><h1>{title}</h1><div className="avatar soft-avatar">{tgUser?.photo_url ? <img src={tgUser.photo_url}/> : (tgUser?.first_name?.[0] || 'د')}</div></header>
}

function HomeView({user,groups,onOpen,onCreate}:{user:User;groups:Group[];onOpen:(g:Group)=>void;onCreate:()=>void}){
  return <><Header title="خانه"/><section className="hero-balance warm-gradient"><span>وضعیت کلی شما</span><strong>{groups.length?'۲,۴۵۰,۰۰۰':'۰'} تومان</strong><p>{groups.length?'نمای کلی حساب‌ها':'اولین حسابت را بساز'}</p><WalletCards size={34}/></section><SectionTitle title="حساب‌های من" action={`${groups.length} حساب`}/><div className="stack">{groups.slice(0,3).map((g,i)=><button key={g.id} className="group-card soft-card" onClick={()=>onOpen(g)}><div className={`group-cover cover-${i%3}`}><span>{i===0?'🏖️':i===1?'🏠':'🎉'}</span></div><div><b>{g.raw_name || g.name}</b><small>{g.role === 'owner' ? '👑 مالک' : '👤 عضو'}</small><em>برای دیدن هزینه‌ها وارد شو</em></div><ChevronLeft/></button>)}</div>{!groups.length&&<div className="empty-state soft-card"><b>هنوز حسابی نداری</b><p>{user.display_name}، اولین حساب را بساز تا هزینه‌ها و اعضا را مدیریت کنی.</p></div>}<button className="primary-neu wide" onClick={onCreate}><Plus/> حساب جدید</button></>
}

function GroupsView({groups,onOpen,onCreate}:{groups:Group[];onOpen:(g:Group)=>void;onCreate:()=>void}){return <><Header title="حساب‌ها"/><div className="stack">{groups.map((g,i)=><button key={g.id} className="group-card soft-card" onClick={()=>onOpen(g)}><div className={`group-cover cover-${i%3}`}><span>{i%2?'🏠':'🌴'}</span></div><div><b>{g.raw_name||g.name}</b><small>{g.role === 'owner'?'مالک حساب':'عضو حساب'}</small></div><ChevronLeft/></button>)}</div><button className="primary-neu wide" onClick={onCreate}><Plus/> ساخت حساب جدید</button></>}

function GroupShell({group,view,onView,onBack,children}:{group:Group;view:GroupView;onView:(v:GroupView)=>void;onBack:()=>void;children:any}){return <div className="app-shell warm-bg"><main className="screen"><Header title={group.raw_name||group.name} back={onBack}/>{children}</main><nav className="bottom-nav soft-nav"><NavItem active={view==='overview'} icon={<Home/>} label="خانه" onClick={()=>onView('overview')}/><NavItem active={view==='members'} icon={<Users/>} label="اعضا" onClick={()=>onView('members')}/><button className="fab warm-gradient" onClick={()=>onView('expense')}><Plus/></button><NavItem active={view==='reports'} icon={<PieChart/>} label="گزارش" onClick={()=>onView('reports')}/><NavItem active={view==='settlements'} icon={<WalletCards/>} label="تسویه" onClick={()=>onView('settlements')}/></nav></div>}

function GroupOverview({members,expenses,report,debts,onView}:{members:Member[];expenses:Expense[];report:any;debts:any;onView:(v:GroupView)=>void}){
  const total = report?.total_amount || 0
  return <><section className="group-hero soft-card"><div><span>{members.length} نفر</span><strong>{money(total)} تومان</strong><small>کل هزینه‌ها</small></div><div className="hero-photo">🏝️</div></section><button className="primary-neu wide" onClick={()=>onView('expense')}><Plus/> ثبت هزینه جدید</button><div className="action-grid"><Action icon={<ReceiptText/>} text="هزینه‌ها"/><Action icon={<WalletCards/>} text="تسویه‌ها" onClick={()=>onView('settlements')}/><Action icon={<Users/>} text="اعضا" onClick={()=>onView('members')}/><Action icon={<PieChart/>} text="گزارش‌ها" onClick={()=>onView('reports')}/><Action icon={<Settings/>} text="دسته‌بندی‌ها" onClick={()=>onView('expense')}/><Action icon={<UserPlus/>} text="دعوت عضو" onClick={()=>onView('members')}/></div><SectionTitle title="آخرین هزینه‌ها" action={`${expenses.length} مورد`}/><div className="stack">{expenses.slice(0,5).map(x=><div className="expense-row soft-card" key={x.id}><div className="expense-icon">{categoryLabels[x.category||'other']?.split(' ')[0]||'🧾'}</div><div><b>{x.title}</b><small>{categoryLabels[x.category||''] || x.category || 'سایر'}</small></div><strong>{money(x.amount)}<small> تومان</small></strong></div>)}</div>{!expenses.length&&<div className="empty-state soft-card"><b>اولین هزینه را ثبت کن</b><p>هنوز هزینه‌ای در این حساب نیست.</p></div>}{debts?.transfers?.length===0&&expenses.length>0&&<div className="success-note soft-card">✅ این حساب در وضعیت تسویه است.</div>}</>
}

function MembersView({group,user,members}:{group:Group;user:User;members:Member[]}){
  const [invite,setInvite]=useState<InvitePayload|null>(null)
  const [busy,setBusy]=useState(false)
  const [note,setNote]=useState('')
  async function loadInvite(){setBusy(true);setNote('');try{setInvite(await api.invite(group.id,user.id))}catch(e){setNote(e instanceof Error?e.message:'ساخت لینک دعوت انجام نشد')}finally{setBusy(false)}}
  const link = invite ? (BOT_USERNAME ? `https://t.me/${BOT_USERNAME}?start=${invite.start_parameter}` : isLocalDemo() ? `https://t.me/dangi_dongi_demo_bot?start=${invite.start_parameter}` : '') : ''
  async function copy(){if(!link)return;await navigator.clipboard.writeText(link);setNote('لینک دعوت کپی شد ✅');haptic()}
  function share(){if(!link)return;const url=`https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(`دعوت به ${group.raw_name||group.name}`)}`;window.Telegram?.WebApp?.openTelegramLink?.(url) || window.open(url,'_blank')}
  return <><div className="panel-title">اعضا</div><div className="list-card soft-card">{members.map(m=><div className="member-row" key={m.user_id}><div className="avatar mini soft-avatar">{m.display_name[0]}</div><b>{m.display_name}</b><span>{m.role==='owner'?'👑 مالک':m.role==='admin'?'🛡 مدیر':'عضو'}</span></div>)}</div><div className="invite-card soft-card"><div className="invite-icon"><UserPlus/></div><div><b>دعوت عضو جدید</b><small>لینک امن مخصوص همین حساب ساخته می‌شود.</small></div>{!invite?<button className="primary-neu" disabled={busy} onClick={loadInvite}>{busy?'در حال ساخت…':'ساخت لینک دعوت'}</button>:<><div className="invite-link">{link||`start=${invite.start_parameter}`}</div><div className="dual-actions"><button className="secondary-neu" onClick={copy} disabled={!link}><Copy/> کپی</button><button className="primary-neu" onClick={share} disabled={!link}><Share2/> ارسال در تلگرام</button></div>{!link&&<div className="mini-warning">برای لینک واقعی، VITE_BOT_USERNAME را در محیط Mini App تنظیم کن.</div>}</>}</div>{note&&<div className="form-note">{note}</div>}</>
}

function SettlementsView({group,user,members,debts,pending,onRefresh}:{group:Group;user:User;members:Member[];debts:any;pending:Settlement[];onRefresh:()=>Promise<void>}){
  const transfers=debts?.transfers||[]
  const [busy,setBusy]=useState<number|null>(null)
  const [payInfo,setPayInfo]=useState<{to:number;profile:PaymentProfile}|null>(null)
  const [note,setNote]=useState('')
  const mine=transfers.filter((x:any)=>x.from_user_id===user.id)
  const incoming=pending.filter(s=>s.to_user_id===user.id)
  const outgoing=pending.filter(s=>s.from_user_id===user.id)
  async function prepare(x:any){setBusy(x.to_user_id);setNote('');try{setPayInfo({to:x.to_user_id,profile:await api.paymentProfile(x.to_user_id)})}catch(e){setNote(e instanceof Error?e.message:'دریافت اطلاعات پرداخت ناموفق بود')}finally{setBusy(null)}}
  async function markPaid(x:any){setBusy(x.to_user_id);try{await api.requestSettlement(group.id,{actor_user_id:user.id,from_user_id:user.id,to_user_id:x.to_user_id,amount:x.amount});setPayInfo(null);setNote('پرداخت اعلام شد و منتظر تأیید بستانکار است ⏳');haptic();await onRefresh()}catch(e){setNote(e instanceof Error?e.message:'ثبت تسویه انجام نشد')}finally{setBusy(null)}}
  async function decide(s:Settlement,ok:boolean){setBusy(s.id);try{ok?await api.confirmSettlement(group.id,s.id,user.id):await api.rejectSettlement(group.id,s.id,user.id);setNote(ok?'تسویه تأیید شد ✅':'تسویه رد شد');haptic();await onRefresh()}catch(e){setNote(e instanceof Error?e.message:'عملیات انجام نشد')}finally{setBusy(null)}}
  return <><div className="panel-title">تسویه‌ها</div>{incoming.length>0&&<><SectionTitle title="نیازمند تأیید شما" action={`${incoming.length} مورد`}/><div className="stack">{incoming.map(s=><div className="debt-card soft-card" key={s.id}><div><b>{memberName(members,s.from_user_id)} پرداخت کرده</b><small>{money(s.amount)} تومان</small></div><div className="settlement-actions"><button className="confirm-btn" disabled={busy===s.id} onClick={()=>decide(s,true)}><Check/> تأیید</button><button className="reject-btn" disabled={busy===s.id} onClick={()=>decide(s,false)}><X/> رد</button></div></div>)}</div></>}
  {outgoing.length>0&&<><SectionTitle title="منتظر تأیید" action={`${outgoing.length} مورد`}/><div className="stack">{outgoing.map(s=><div className="debt-card soft-card" key={s.id}><div><b>پرداخت به {memberName(members,s.to_user_id)}</b><small>{money(s.amount)} تومان</small></div><span className="pending-pill">⏳ منتظر تأیید</span></div>)}</div></>}
  <SectionTitle title="پیشنهاد تسویه" action={`${transfers.length} مسیر`}/>{transfers.length===0?<div className="success-note soft-card">این حساب کاملاً تسویه است ✅</div>:<div className="stack">{transfers.map((x:any,i:number)=><div className="debt-card soft-card" key={i}><div><b>{x.from_name} → {x.to_name}</b><small>{money(x.amount)} تومان</small></div>{x.from_user_id===user.id?<button className="soft action-pill" disabled={busy===x.to_user_id} onClick={()=>prepare(x)}><CreditCard/> پرداخت</button>:<span className="muted mini">مسیر پیشنهادی</span>}</div>)}</div>}
  {payInfo&&<div className="payment-sheet soft-card"><button className="sheet-close" onClick={()=>setPayInfo(null)}><X/></button><h3>اطلاعات پرداخت {memberName(members,payInfo.to)}</h3><PaymentDetails profile={payInfo.profile}/><button className="primary-neu wide" onClick={()=>{const x=mine.find((t:any)=>t.to_user_id===payInfo.to);if(x)markPaid(x)}}>✅ پرداخت کردم</button><small>تغییر مانده فقط بعد از تأیید دریافت‌کننده انجام می‌شود.</small></div>}{note&&<div className="form-note">{note}</div>}</>
}

function PaymentDetails({profile}:{profile:PaymentProfile}){return <div className="payment-details">{profile.account_holder&&<div><span>صاحب حساب</span><b>{profile.account_holder}</b></div>}{profile.bank_name&&<div><span>بانک</span><b>{profile.bank_name}</b></div>}{profile.card_number&&<div><span>شماره کارت</span><b dir="ltr">{profile.card_number}</b></div>}{profile.iban&&<div><span>شبا</span><b dir="ltr">{profile.iban}</b></div>}{profile.account_number&&<div><span>شماره حساب</span><b dir="ltr">{profile.account_number}</b></div>}{!profile.card_number&&!profile.iban&&!profile.account_number&&<div className="mini-warning">اطلاعات پرداخت این کاربر هنوز ثبت نشده است.</div>}</div>}

function ReportsView({report,debts}:{report:any;debts:any}){
  const [mode,setMode]=useState<'expenses'|'debts'>('expenses')
  const cats=report?.categories||[];const total=Number(report?.total_amount||0)
  const balances=debts?.balances||[];const transfers=debts?.transfers||[]
  return <><div className="segmented soft-card"><button className={mode==='expenses'?'active':''} onClick={()=>setMode('expenses')}>هزینه‌ها</button><button className={mode==='debts'?'active':''} onClick={()=>setMode('debts')}>بدهی‌ها</button></div>{mode==='expenses'?<><section className="report-summary soft-card"><span>کل هزینه‌ها</span><strong>{money(total)} تومان</strong><small>{report?.expense_count||0} هزینه ثبت‌شده</small></section><div className="report-card soft-card"><h3>هزینه‌ها بر اساس دسته‌بندی</h3><div className="donut"/><div className="legend">{cats.slice(0,8).map((c:any)=><div key={c.category}><span>{categoryLabels[c.category]||c.category}</span><b>{money(c.amount)} تومان · {total?Math.round(Number(c.amount)/total*100):0}٪</b></div>)}</div>{!cats.length&&<p className="muted">هنوز هزینه‌ای ثبت نشده.</p>}</div></>:<><div className="report-card soft-card"><h3>مانده اعضا</h3><div className="balance-list">{balances.map((b:any)=><div key={b.user_id}><span>{b.display_name}</span><b className={b.status}>{b.status==='debtor'?'−':b.status==='creditor'?'+':''}{money(Math.abs(Number(b.balance)))} تومان</b></div>)}</div></div><div className="report-card soft-card"><h3>مسیر پیشنهادی تسویه</h3><div className="balance-list">{transfers.map((t:any,i:number)=><div key={i}><span>{t.from_name} → {t.to_name}</span><b>{money(t.amount)} تومان</b></div>)}</div>{!transfers.length&&<p className="muted">همه تسویه‌اند ✅</p>}</div></>}</>
}

function ExpenseForm({group,user,members,categories,onSaved}:{group:Group;user:User;members:Member[];categories:GroupCategory[];onSaved:()=>Promise<void>}){
  const [title,setTitle]=useState('');const [amount,setAmount]=useState('');const [payer,setPayer]=useState(user.id);const [category,setCategory]=useState('food');const [selected,setSelected]=useState<number[]>(members.map(m=>m.user_id));const [mode,setMode]=useState<SplitMode>('equal');const [values,setValues]=useState<Record<number,string>>({});const [busy,setBusy]=useState(false);const [note,setNote]=useState('')
  const sum=useMemo(()=>selected.reduce((s,id)=>s+Number(values[id]||0),0),[selected,values])
  function selectMode(next:SplitMode){setMode(next);setValues({});haptic()}
  async function submit(){
    setNote('')
    if(!title.trim()||!amount||!selected.length){setNote('عنوان، مبلغ و حداقل یک شرکت‌کننده لازم است.');return}
    if(mode==='percentage'&&Math.abs(sum-100)>.001){setNote('مجموع درصدها باید دقیقاً ۱۰۰ باشد.');return}
    if(mode==='exact'&&Math.abs(sum-Number(amount))>.001){setNote('مجموع مبلغ‌های ثابت باید دقیقاً برابر کل هزینه باشد.');return}
    if((mode==='shares'||mode==='percentage'||mode==='exact')&&selected.some(id=>Number(values[id]||0)<=0)){setNote('برای همه افراد مقدار مثبت وارد کن.');return}
    const splitValues=mode==='equal'?null:Object.fromEntries(selected.map(id=>[id,Number(values[id])]))
    setBusy(true)
    try{await api.createExpense(group.id,{actor_user_id:user.id,paid_by_user_id:payer,amount:Number(amount),title:title.trim(),participant_user_ids:selected,split_mode:mode,split_values:splitValues,category});haptic();await onSaved()}catch(e){setNote(e instanceof Error?e.message:'ثبت هزینه انجام نشد')}finally{setBusy(false)}
  }
  const allCategories=[...Object.entries(categoryLabels).map(([value,label])=>({value,label})),...categories.map(c=>({value:c.name,label:`✨ ${c.name}`}))]
  return <div className="form-card soft-card"><div className="form-title"><div><small>حساب</small><h3>{group.raw_name||group.name}</h3></div><ReceiptText/></div><label>عنوان هزینه<input value={title} onChange={e=>setTitle(e.target.value)} placeholder="مثلاً شام رستوران"/></label><label>مبلغ (تومان)<input inputMode="numeric" value={amount} onChange={e=>setAmount(e.target.value.replace(/\D/g,''))} placeholder="1,850,000"/></label><label>پرداخت‌کننده<select value={payer} onChange={e=>setPayer(Number(e.target.value))}>{members.map(m=><option value={m.user_id} key={m.user_id}>{m.display_name}</option>)}</select></label><label>دسته‌بندی<select value={category} onChange={e=>setCategory(e.target.value)}>{allCategories.map(c=><option value={c.value} key={c.value}>{c.label}</option>)}</select></label><div className="field-label">بین چه کسانی تقسیم شود؟</div><div className="participant-grid">{members.map(m=><label className={`participant-chip ${selected.includes(m.user_id)?'selected':''}`} key={m.user_id}><input type="checkbox" checked={selected.includes(m.user_id)} onChange={()=>setSelected(s=>s.includes(m.user_id)?s.filter(x=>x!==m.user_id):[...s,m.user_id])}/><span>{selected.includes(m.user_id)?'✓':'+'}</span>{m.display_name}</label>)}</div><div className="field-label">نحوه تقسیم</div><div className="split-grid"><button className={mode==='equal'?'active':''} onClick={()=>selectMode('equal')}>⚖️ مساوی</button><button className={mode==='percentage'?'active':''} onClick={()=>selectMode('percentage')}>٪ درصدی</button><button className={mode==='shares'?'active':''} onClick={()=>selectMode('shares')}>🔢 سهمی</button><button className={mode==='exact'?'active':''} onClick={()=>selectMode('exact')}>💵 مبلغ ثابت</button></div>{mode!=='equal'&&<div className="split-values">{selected.map(id=><label key={id}><span>{memberName(members,id)}</span><input inputMode="decimal" value={values[id]||''} onChange={e=>setValues(v=>({...v,[id]:e.target.value.replace(/[^0-9.]/g,'')}))} placeholder={mode==='percentage'?'درصد':mode==='shares'?'تعداد سهم':'تومان'}/></label>)}<div className="split-total"><span>مجموع</span><b>{mode==='percentage'?`${sum.toLocaleString('fa-IR')}٪`:mode==='shares'?`${sum.toLocaleString('fa-IR')} سهم`:`${money(sum)} تومان`}</b></div></div>}{note&&<div className="form-error"><AlertCircle/>{note}</div>}<button className="primary-neu wide" disabled={busy} onClick={submit}>{busy?'در حال ثبت…':'ثبت هزینه'}</button></div>
}

function QuickExpense({groups,onOpen,onCreate}:{groups:Group[];onOpen:(g:Group)=>void;onCreate:()=>void}){return <><Header title="ثبت هزینه"/>{groups.length?<><p className="muted">حساب موردنظر را انتخاب کن.</p><div className="stack">{groups.map(g=><button className="group-card simple soft-card" key={g.id} onClick={()=>onOpen(g)}><b>{g.raw_name||g.name}</b><ChevronLeft/></button>)}</div></>:<div className="empty-state soft-card"><b>اول باید حساب بسازی</b><button className="primary-neu" onClick={onCreate}><Plus/> ساخت حساب</button></div>}</>}
function GlobalReports({groups,onOpen}:{groups:Group[];onOpen:(g:Group)=>void}){return <><Header title="گزارش‌ها"/><p className="muted">برای گزارش زنده، یک حساب را انتخاب کن.</p><div className="stack">{groups.map(g=><button className="group-card simple soft-card" key={g.id} onClick={()=>onOpen(g)}><div><b>{g.raw_name||g.name}</b><small>هزینه‌ها، مانده اعضا و مسیر تسویه</small></div><PieChart/></button>)}</div></>}

function ProfileView({user}:{user:User}){
  const tgUser=telegramUser();const [profile,setProfile]=useState<PaymentProfile|null>(null);const [draft,setDraft]=useState<PaymentProfile>({reminder_enabled:true});const [editing,setEditing]=useState(false);const [busy,setBusy]=useState(false);const [note,setNote]=useState('')
  useEffect(()=>{api.paymentProfile(user.id).then(p=>{setProfile(p);setDraft(p)}).catch(e=>setNote(e instanceof Error?e.message:'خطا در پروفایل'))},[user.id])
  async function save(){setBusy(true);setNote('');try{const payload={bank_name:draft.bank_name||null,account_holder:draft.account_holder||null,card_number:draft.card_number||null,iban:draft.iban||null,account_number:draft.account_number||null,reminder_enabled:draft.reminder_enabled};const p=await api.savePaymentProfile(user.id,payload);setProfile(p);setDraft(p);setEditing(false);setNote('اطلاعات پرداخت ذخیره شد ✅');haptic()}catch(e){setNote(e instanceof Error?e.message:'ذخیره انجام نشد')}finally{setBusy(false)}}
  async function toggle(){const next={...(profile||draft),reminder_enabled:!(profile||draft).reminder_enabled};setBusy(true);try{const p=await api.savePaymentProfile(user.id,next);setProfile(p);setDraft(p);haptic()}finally{setBusy(false)}}
  return <><Header title="پروفایل من"/><div className="profile-head"><div className="avatar xl soft-avatar">{tgUser?.photo_url?<img src={tgUser.photo_url}/>:user.display_name[0]}</div><h2>{user.display_name}</h2><small>{tgUser?.username?`@${tgUser.username}`:'حساب تلگرام'}</small></div>{!editing?<><div className="profile-payment soft-card"><div className="card-head"><div><small>اطلاعات دریافت وجه</small><h3>{profile?.bank_name||'هنوز تکمیل نشده'}</h3></div><CreditCard/></div>{profile&&<PaymentDetails profile={profile}/>}<button className="secondary-neu wide" onClick={()=>setEditing(true)}>ویرایش اطلاعات پرداخت</button></div><div className="list-card settings-list soft-card"><button disabled={busy} onClick={toggle}>{profile?.reminder_enabled?'🔔 یادآوری بدهی روشن است':'🔕 یادآوری بدهی خاموش است'} <span>{profile?.reminder_enabled?'خاموش کن':'روشن کن'}</span></button><button>🔐 امنیت ورود با تلگرام <ShieldCheck/></button><button>🎧 پشتیبانی <ChevronLeft/></button></div></>:<div className="form-card soft-card"><h3>ویرایش اطلاعات پرداخت</h3><label>نام بانک<input value={draft.bank_name||''} onChange={e=>setDraft(d=>({...d,bank_name:e.target.value}))}/></label><label>نام صاحب حساب<input value={draft.account_holder||''} onChange={e=>setDraft(d=>({...d,account_holder:e.target.value}))}/></label><label>شماره کارت<input dir="ltr" value={draft.card_number||''} onChange={e=>setDraft(d=>({...d,card_number:e.target.value.replace(/\D/g,'')}))}/></label><label>شماره شبا<input dir="ltr" value={draft.iban||''} onChange={e=>setDraft(d=>({...d,iban:e.target.value.toUpperCase().replace(/\s/g,'')}))}/></label><label>شماره حساب<input dir="ltr" value={draft.account_number||''} onChange={e=>setDraft(d=>({...d,account_number:e.target.value.replace(/\s/g,'')}))}/></label><div className="dual-actions"><button className="secondary-neu" onClick={()=>{setDraft(profile||{reminder_enabled:true});setEditing(false)}}><X/> انصراف</button><button className="primary-neu" disabled={busy} onClick={save}><Save/> {busy?'در حال ذخیره…':'ذخیره'}</button></div></div>}{note&&<div className="form-note">{note}</div>}</>
}

function BottomNav({tab,onChange}:{tab:Tab;onChange:(t:Tab)=>void}){return <nav className="bottom-nav soft-nav"><NavItem active={tab==='home'} icon={<Home/>} label="خانه" onClick={()=>onChange('home')}/><NavItem active={tab==='groups'} icon={<ReceiptText/>} label="حساب‌ها" onClick={()=>onChange('groups')}/><button className="fab warm-gradient" onClick={()=>onChange('expense')}><Plus/></button><NavItem active={tab==='reports'} icon={<PieChart/>} label="گزارش" onClick={()=>onChange('reports')}/><NavItem active={tab==='profile'} icon={<CircleUserRound/>} label="پروفایل" onClick={()=>onChange('profile')}/></nav>}
function NavItem({active,icon,label,onClick}:{active:boolean;icon:any;label:string;onClick:()=>void}){return <button className={`nav-item ${active?'active':''}`} onClick={onClick}>{icon}<span>{label}</span></button>}
function Action({icon,text,onClick}:{icon:any;text:string;onClick?:()=>void}){return <button className="action soft-card" onClick={onClick}>{icon}<span>{text}</span></button>}
function SectionTitle({title,action}:{title:string;action:string}){return <div className="section-title"><b>{title}</b><span>{action}</span></div>}
