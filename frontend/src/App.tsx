import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { AlertsPage } from '@/pages/AlertsPage'
import { SettingsPage } from '@/pages/SettingsPage'
import { WatchlistPage } from '@/pages/WatchlistPage'

function App() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="mx-auto max-w-[1400px] px-6 py-6">
        {/* Top bar — branding + connection status */}
        <header className="mb-4 flex flex-wrap items-center gap-3 border-b border-rs-border pb-4">
          <div className="size-5 rounded-md rs-brand-mark" />
          <div className="text-[14px] font-semibold text-rs-text">Riven Scanner</div>
          <span className="text-rs-mute text-[12px]">·</span>
          <span className="text-[12px] text-rs-dim">warframe.market · PC</span>
          <div className="ml-auto flex items-center gap-2 text-[12px] text-rs-dim">
            <span className="inline-block size-1.5 rounded-full bg-rs-success" />
            Connected
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
