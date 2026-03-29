import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import Navbar from "@/components/Navbar";
import UploadPage from "@/pages/UploadPage";
import DashboardPage from "@/pages/DashboardPage";
import HistoryPage from "@/pages/HistoryPage";

function App() {
  return (
    <div className="min-h-screen" style={{ background: 'var(--bg-primary)' }}>
      <BrowserRouter>
        <Navbar />
        <main className="pt-16">
          <Routes>
            <Route path="/" element={<UploadPage />} />
            <Route path="/analysis/:id" element={<DashboardPage />} />
            <Route path="/history" element={<HistoryPage />} />
          </Routes>
        </main>
      </BrowserRouter>
      <Toaster position="bottom-right" theme="dark" />
    </div>
  );
}

export default App;
