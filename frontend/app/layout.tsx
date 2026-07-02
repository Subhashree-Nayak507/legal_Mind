import { AuthProvider } from '@/app/context/AuthContext'
import './globals.css'

export const metadata = { title: 'LegalMind', description: 'Legal Document AI Assistant' }
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  )
}
