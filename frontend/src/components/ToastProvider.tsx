import { Alert, Snackbar } from "@mui/material";
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

export type ToastSeverity = "success" | "error" | "info" | "warning";

interface ToastContextValue {
  notify: (severity: ToastSeverity, message: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

// 사이트 전역 성공/실패 토스트(2026-09-07 요청) — 저장·삭제·실행 등 사용자가 누른 동작이
// 실제로 반영됐는지 화면에 반드시 보여준다("저장한 줄 알았는데 안 됐더라" 문제 방지, 71번
// 항목의 "조용한 실패" 교훈과 같은 이유). 페이지마다 개별 Snackbar를 두지 않고 App.tsx
// 최상단에서 한 번만 마운트해 어디서든 useToast()로 띄운다.
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<{ severity: ToastSeverity; message: string; key: number } | null>(null);

  const notify = useCallback((severity: ToastSeverity, message: string) => {
    setToast({ severity, message, key: Date.now() });
  }, []);

  return (
    <ToastContext.Provider value={{ notify }}>
      {children}
      <Snackbar
        key={toast?.key}
        open={toast !== null}
        autoHideDuration={5000}
        onClose={() => setToast(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        {toast ? (
          <Alert severity={toast.severity} onClose={() => setToast(null)} sx={{ width: "100%" }} variant="filled">
            {toast.message}
          </Alert>
        ) : undefined}
      </Snackbar>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast는 ToastProvider 안에서만 쓸 수 있습니다.");
  return ctx;
}
