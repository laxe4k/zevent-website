<script setup lang="ts">
type Amount = { number?: number }
type Streamer = {
  display?: string
  twitch?: string
  online?: boolean
  game?: string
  location?: string
  profileUrl?: string
  donationUrl?: string
  viewersAmount?: Amount
  donationAmount?: Amount
}
type Dashboard = {
  donationAmount?: Amount
  viewersCount?: Amount
  globalDonationUrl?: string
  live?: Streamer[]
}

const config = useRuntimeConfig()
const dashboard = ref<Dashboard>()
const search = ref('')
const onlineOnly = ref(false)
const locationFilter = ref('')
const sort = ref('donations')
const loading = ref(true)
const refreshing = ref(false)
const error = ref('')
const connection = ref<'connecting' | 'live' | 'backup'>('connecting')
const lastUpdate = ref<Date>()
const scoreboardSticky = ref(false)
const directoryTopEl = ref<HTMLElement>()
let eventSource: EventSource | undefined
let refreshTimer: ReturnType<typeof setInterval> | undefined
let syncRequest: Promise<void> | undefined
let scrollHandler: (() => void) | undefined
let loadMoreObserver: IntersectionObserver | undefined

const PAGE_SIZE = 30
const visibleCount = ref(PAGE_SIZE)
const sentinelEl = ref<HTMLElement>()

const visibleStreamers = computed(() => streamers.value.slice(0, visibleCount.value))
const hasMore = computed(() => visibleCount.value < streamers.value.length)

watch([search, onlineOnly, locationFilter, sort], () => { visibleCount.value = PAGE_SIZE })

const money = new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR' })
const number = new Intl.NumberFormat('fr-FR')

function donations(s: Streamer) { return Number(s.donationAmount?.number || 0) }
function viewers(s: Streamer) { return Number(s.viewersAmount?.number || 0) }
function formatMoney(a?: Amount) { return money.format(Number(a?.number || 0)) }
function formatNumber(v?: Amount | number) { return number.format(typeof v === 'number' ? v : Number(v?.number || 0)) }

const allLive = computed(() => {
  const list = dashboard.value?.live || []
  const globalTotal = Number(dashboard.value?.donationAmount?.number || 0)
  const streamersSum = list.reduce((sum, s) => sum + donations(s), 0)
  const diff = Math.max(globalTotal - streamersSum, 0)
  if (diff <= 0) return list
  return list.map((s) => {
    if (s.twitch !== 'zevent') return s
    const current = donations(s)
    return { ...s, donationAmount: { number: current + diff } }
  })
})

const onlineCount = computed(() => allLive.value.filter((s) => s.online).length)
const totalCount = computed(() => allLive.value.length)
const connectionLabel = computed(() => {
  if (connection.value === 'live') return 'Flux direct actif'
  if (connection.value === 'backup') return 'Synchronisation automatique'
  return 'Connexion au flux'
})

const donationTotal = computed(() => Number(dashboard.value?.donationAmount?.number || 0))

const topByDonations = computed(() => {
  const sorted = [...allLive.value]
    .filter((s) => donations(s) > 0)
    .sort((a, b) => donations(b) - donations(a))
    .slice(0, 6)
  const max = donations(sorted[0] || {})
  return sorted.map((s) => ({
    name: s.display || s.twitch || '?',
    amount: donations(s),
    pct: max > 0 ? (donations(s) / max) * 100 : 0,
    online: !!s.online,
  }))
})

const topByViewers = computed(() => {
  const sorted = [...allLive.value]
    .filter((s) => viewers(s) > 0)
    .sort((a, b) => viewers(b) - viewers(a))
    .slice(0, 6)
  const max = viewers(sorted[0] || {})
  return sorted.map((s) => ({
    name: s.display || s.twitch || '?',
    viewers: viewers(s),
    pct: max > 0 ? (viewers(s) / max) * 100 : 0,
    online: !!s.online,
  }))
})

const streamers = computed(() => {
  const needle = search.value.trim().toLocaleLowerCase()
  return [...allLive.value]
    .filter((s) => {
      const match = `${s.display || ''} ${s.twitch || ''}`.toLowerCase().includes(needle)
      const matchLocation = !locationFilter.value || s.location === locationFilter.value
      return match && matchLocation && (!onlineOnly.value || s.online)
    })
    .sort((a, b) => {
      if (sort.value === 'viewers') return viewers(b) - viewers(a)
      if (sort.value === 'game') return Number(b.online) - Number(a.online) || (a.game || 'ZZZ').localeCompare(b.game || 'ZZZ', 'fr') || (a.display || '').localeCompare(b.display || '', 'fr')
      if (sort.value === 'name') return (a.display || '').localeCompare(b.display || '', 'fr')
      if (sort.value === 'online') return Number(b.online) - Number(a.online) || donations(b) - donations(a)
      return donations(b) - donations(a)
    })
})

function sync() {
  if (syncRequest) return syncRequest
  refreshing.value = true
  syncRequest = $fetch<Dashboard>('/api/raw', { baseURL: config.public.apiBase })
    .then((d) => { dashboard.value = d; lastUpdate.value = new Date(); error.value = '' })
    .catch(() => { error.value = 'Mise a jour indisponible.' })
    .finally(() => { loading.value = false; refreshing.value = false; syncRequest = undefined })
  return syncRequest
}

function connectLiveFeed() {
  eventSource = new EventSource(`${config.public.apiBase}/events`)
  eventSource.onopen = () => { connection.value = 'live' }
  eventSource.onmessage = (e) => {
    try {
      const m = JSON.parse(e.data) as { data?: Dashboard }
      if (!m.data) return
      dashboard.value = m.data; lastUpdate.value = new Date(); error.value = ''; loading.value = false; connection.value = 'live'
    } catch { connection.value = 'backup' }
  }
  eventSource.onerror = () => { connection.value = 'backup' }
}

onMounted(() => {
  sync(); connectLiveFeed(); refreshTimer = setInterval(sync, 15_000)
  nextTick(() => {
    scrollHandler = () => {
      if (!directoryTopEl.value) return
      scoreboardSticky.value = directoryTopEl.value.getBoundingClientRect().top <= 0
    }
    window.addEventListener('scroll', scrollHandler, { passive: true })

    nextTick(() => {
      loadMoreObserver = new IntersectionObserver((entries) => {
        if (entries[0]?.isIntersecting && hasMore.value) {
          visibleCount.value += PAGE_SIZE
        }
      }, { rootMargin: '400px' })
      if (sentinelEl.value) loadMoreObserver.observe(sentinelEl.value)
    })
  })
})
onBeforeUnmount(() => {
  eventSource?.close(); if (refreshTimer) clearInterval(refreshTimer)
  if (scrollHandler) window.removeEventListener('scroll', scrollHandler)
  loadMoreObserver?.disconnect()
})

const AnimatedNumber = defineComponent({
  props: { value: { type: Number, required: true }, format: { type: String, default: 'number' } },
  setup(props) {
    const display = ref(props.value)
    const prev = ref(props.value)
    let raf: number | undefined
    let startTime = 0
    const duration = 600

    function animate(now: number) {
      if (!startTime) startTime = now
      const progress = Math.min((now - startTime) / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 3)
      display.value = prev.value + (props.value - prev.value) * eased
      if (progress < 1) raf = requestAnimationFrame(animate)
    }

    watch(() => props.value, () => {
      prev.value = display.value
      startTime = 0
      if (raf) cancelAnimationFrame(raf)
      raf = requestAnimationFrame(animate)
    })

    onBeforeUnmount(() => { if (raf) cancelAnimationFrame(raf) })

    return () => {
      const raw = props.format === 'money' ? display.value : Math.round(display.value)
      const formatted = props.format === 'money' ? money.format(raw) : number.format(raw)
      return h('span', { style: 'all:unset' }, formatted)
    }
  }
})
</script>

<template>
  <main class="dashboard">
    <header class="topbar">
      <a class="wordmark" href="/">
        <img src="https://zevent.fr/assets/logo-2026-Ce9cgF9k.png" alt="ZEvent" class="wordmark__logo">
      </a>
      <div class="topbar__right">
        <a href="https://boutique.zevent.fr/" target="_blank" rel="noreferrer" class="topbar__btn">Boutique</a>
        <a href="https://zevent.fr/don" target="_blank" rel="noreferrer" class="topbar__btn">Donation</a>
        <a href="https://place.zevent.fr/" target="_blank" rel="noreferrer" class="topbar__btn">ZPlace</a>
      </div>
    </header>

    <section id="top" class="hero">
      <a href="https://zevent.fr/" target="_blank" rel="noreferrer"><img src="https://zevent.fr/assets/banner-2026-2-Bqkgwhtq.webp" alt="ZEvent 2026" class="hero__banner" loading="eager"></a>
      <div class="hero__inner">
        <div class="chart">
          <div class="chart__head">
            <span class="chart__label">Top 6 cagnotte</span>
            <span v-if="donationTotal > 0" class="chart__total"><AnimatedNumber :value="donationTotal" format="money" /></span>
          </div>
          <div class="chart__bars">
            <div v-for="(item, i) in topByDonations" :key="item.name" class="chart__row">
              <span class="chart__rank">{{ i + 1 }}</span>
              <span class="chart__name">{{ item.name }}</span>
              <div class="chart__track">
                <div class="chart__fill" :style="{ width: item.pct + '%' }" />
              </div>
              <span class="chart__val"><AnimatedNumber :value="item.amount" format="money" /></span>
            </div>
            <p v-if="topByDonations.length === 0" class="chart__empty">Aucune donation enregistree.</p>
          </div>
        </div>
        <div class="chart">
          <div class="chart__head">
            <span class="chart__label">Top 6 audience</span>
            <span v-if="dashboard?.viewersCount?.number" class="chart__total"><AnimatedNumber :value="Number(dashboard.viewersCount.number)" /></span>
          </div>
          <div class="chart__bars">
            <div v-for="(item, i) in topByViewers" :key="item.name" class="chart__row">
              <span class="chart__rank">{{ i + 1 }}</span>
              <span class="chart__name">{{ item.name }}</span>
              <div class="chart__track">
                <div class="chart__fill" :style="{ width: item.pct + '%' }" />
              </div>
              <span class="chart__val"><AnimatedNumber :value="item.viewers" /></span>
            </div>
            <p v-if="topByViewers.length === 0" class="chart__empty">Aucun viewer enregistre.</p>
          </div>
        </div>
      </div>
    </section>

    <section ref="scoreboardEl" class="scoreboard" aria-live="polite">
      <article class="card card--hero">
        <span class="card__label">Cagnotte globale</span>
        <strong class="card__big"><AnimatedNumber :value="Number(dashboard?.donationAmount?.number || 0)" format="money" /></strong>
        <a v-if="dashboard?.globalDonationUrl" class="card__link" :href="dashboard.globalDonationUrl" target="_blank" rel="noreferrer">Faire un don au ZEVENT</a>
      </article>
      <article class="card">
        <span class="card__label">Audience</span>
        <strong class="card__big"><AnimatedNumber :value="Number(dashboard?.viewersCount?.number || 0)" /></strong>
        <small class="card__sub">Spectateurs cumules</small>
      </article>
      <article class="card">
        <span class="card__label">On air</span>
        <strong class="card__big"><AnimatedNumber :value="onlineCount" /></strong>
        <small class="card__sub">Sur {{ formatNumber(totalCount) }} streamers</small>
      </article>
    </section>

    <div class="floating-bar" :class="{ 'floating-bar--show': scoreboardSticky }">
      <div class="floating-bar__inner">
        <div class="floating-bar__item floating-bar__item--hero">
          <span class="floating-bar__label">Cagnotte</span>
          <strong class="floating-bar__val"><AnimatedNumber :value="Number(dashboard?.donationAmount?.number || 0)" format="money" /></strong>
        </div>
        <div class="floating-bar__item">
          <span class="floating-bar__label">Audience</span>
          <strong class="floating-bar__val"><AnimatedNumber :value="Number(dashboard?.viewersCount?.number || 0)" /></strong>
        </div>
        <div class="floating-bar__item">
          <span class="floating-bar__label">On air</span>
          <strong class="floating-bar__val"><AnimatedNumber :value="onlineCount" /></strong>
        </div>
      </div>
    </div>

    <section class="directory">
      <div ref="directoryTopEl" class="directory__top">
        <div>
          <p class="kicker">Annuaire live</p>
          <h2>Les streamers</h2>
        </div>
        <p v-if="lastUpdate" class="last-update">Mis a jour a {{ lastUpdate.toLocaleTimeString('fr-FR') }}</p>
      </div>

      <form class="filters" @submit.prevent="sync">
        <div class="filters__search">
          <svg class="filters__icon" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2"><circle cx="8.5" cy="8.5" r="5.5"/><path d="M13 13l4 4"/></svg>
          <input v-model="search" type="search" placeholder="Rechercher un streamer..." autocomplete="off">
        </div>
        <div class="filters__right">
          <label class="toggle">
            <input v-model="onlineOnly" type="checkbox">
            <span class="toggle__track"><span class="toggle__thumb" /></span>
            <span>En live</span>
          </label>
          <div class="filters__sort">
            <select v-model="locationFilter">
              <option value="">Tous</option>
              <option value="LAN">Sur place</option>
              <option value="Online">À distance</option>
            </select>
          </div>
          <div class="filters__sort">
            <select v-model="sort">
              <option value="donations">Donations</option>
              <option value="viewers">Audience</option>
              <option value="game">Jeux</option>
              <option value="name">Nom</option>
            </select>
          </div>
        </div>
      </form>

      <p v-if="error" class="msg msg--err">{{ error }}</p>
      <p v-else-if="loading" class="msg">Connexion aux donnees ZEvent...</p>
      <p v-else class="msg">{{ formatNumber(streamers.length) }} profils affiches.</p>

      <div class="grid" :aria-busy="loading">
        <article v-for="s in visibleStreamers" :key="s.twitch || s.display" class="scard">
          <img
            v-if="s.profileUrl"
            class="scard__avatar"
            :src="s.profileUrl"
            :alt="`Portrait de ${s.display || s.twitch}`"
            loading="eager"
            decoding="sync"
          >
          <div v-else class="scard__avatar scard__avatar--fb">{{ s.display?.slice(0, 1) || '?' }}</div>

          <div class="scard__head">
            <div>
              <h3>{{ s.display || s.twitch }}</h3>
              <p v-if="s.twitch" class="scard__twitch">@{{ s.twitch }}</p>
            </div>
            <span class="scard__badge" :class="{ 'scard__badge--on': s.online }">{{ s.online ? 'En live' : 'Hors ligne' }}</span>
          </div>

          <p class="scard__game">{{ s.game || 'A venir' }}<span v-if="s.location"> &middot; {{ s.location === 'LAN' ? 'Sur place' : 'À distance' }}</span></p>

          <div class="scard__stats">
            <div><span>Viewers</span><strong><AnimatedNumber :value="viewers(s)" /></strong></div>
            <div><span>Collecte</span><strong><AnimatedNumber :value="Number(s.donationAmount?.number || 0)" format="money" /></strong></div>
          </div>

          <nav class="scard__links" :aria-label="`Liens de ${s.display || s.twitch}`">
            <a v-if="s.twitch" :href="`https://twitch.tv/${s.twitch}`" target="_blank" rel="noreferrer">Twitch</a>
            <a v-if="s.donationUrl" :href="s.donationUrl" target="_blank" rel="noreferrer">Donner</a>
          </nav>
        </article>
      </div>

      <div ref="sentinelEl" style="height:1px" />

      <button v-if="hasMore && !loading" class="load-more" @click="visibleCount += PAGE_SIZE">
        Afficher plus ({{ visibleCount }} / {{ streamers.length }})
      </button>

      <p v-if="!loading && streamers.length === 0" class="msg">Aucun streamer ne correspond a cette recherche.</p>
    </section>
  </main>
</template>
