import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { AlertsPage } from '@/pages/AlertsPage'
import { SettingsPage } from '@/pages/SettingsPage'
import { WatchlistPage } from '@/pages/WatchlistPage'

function App() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="mx-auto max-w-[1400px] px-6 py-6">
        {/* Top bar — branding + connection status */}
        <header className="mb-6 flex flex-wrap items-center gap-4 border-b border-rs-border/50 pb-5 shadow-[0_1px_30px_-10px_rgba(217,70,239,0.15)] relative">
          <div className="absolute top-0 left-0 w-1/4 h-[1px] bg-gradient-to-r from-transparent via-rs-accent to-transparent shadow-[0_0_10px_rgba(217,70,239,0.5)]"></div>
          <div className="size-6 rounded-md rs-brand-mark shadow-[0_0_10px_rgba(217,70,239,0.4)]" />
          <div className="text-[16px] tracking-wide uppercase font-bold bg-clip-text text-transparent bg-gradient-to-r from-white to-rs-dim">Riven Scanner</div>
          <span className="text-rs-mute text-[12px]">/</span>
          <span className="text-[11px] font-mono tracking-widest text-rs-dim uppercase">warframe.market // PC</span>
          <div className="ml-auto flex items-center gap-2 text-[11px] font-mono uppercase tracking-widest text-rs-success bg-rs-success/10 px-3 py-1 rounded-full border border-rs-success/30">
            <span className="inline-block size-1.5 rounded-full bg-rs-success shadow-[0_0_5px_rgba(16,185,129,0.8)] animate-pulse" />
            Uplink Active
          </div>
        </header>

        <Tabs defaultValue="alerts" className="w-full">
          <TabsList className="bg-transparent border-b border-rs-border w-full justify-start rounded-none p-0 h-auto gap-6">
            <TabsTrigger
              value="alerts"
              className="rounded-none border-b-2 border-transparent bg-transparent px-0 py-3 text-[13px] text-rs-dim shadow-none data-[state=active]:border-rs-accent data-[state=active]:bg-transparent data-[state=active]:text-rs-text data-[state=active]:shadow-none"
            >
              Alerts
            </TabsTrigger>
            <TabsTrigger
              value="watchlist"
              className="rounded-none border-b-2 border-transparent bg-transparent px-0 py-3 text-[13px] text-rs-dim shadow-none data-[state=active]:border-rs-accent data-[state=active]:bg-transparent data-[state=active]:text-rs-text data-[state=active]:shadow-none"
            >
              Watchlist
            </TabsTrigger>
            <TabsTrigger
              value="settings"
              className="rounded-none border-b-2 border-transparent bg-transparent px-0 py-3 text-[13px] text-rs-dim shadow-none data-[state=active]:border-rs-accent data-[state=active]:bg-transparent data-[state=active]:text-rs-text data-[state=active]:shadow-none"
            >
              Settings
            </TabsTrigger>
          </TabsList>

          <TabsContent value="alerts" className="mt-6">
            <AlertsPage />
          </TabsContent>

          <TabsContent value="watchlist" className="mt-6">
            <WatchlistPage />
          </TabsContent>

          <TabsContent value="settings" className="mt-6">
            <SettingsPage />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  )
}

export default App
