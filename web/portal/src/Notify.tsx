import {createContext, useCallback, useContext} from 'react';
import {Toaster, toast} from 'sonner';

type Notify = (body: string, type?: 'info' | 'error') => void;
const NotifyContext = createContext<Notify>(() => undefined);

export function useNotify() {
  return useContext(NotifyContext);
}

export function NotifyProvider({children}: {children: React.ReactNode}) {
  const notify = useCallback<Notify>((body, type = 'info') => {
    if (type === 'error') {
      toast.error(body);
    } else {
      toast(body);
    }
  }, []);
  return (
    <NotifyContext.Provider value={notify}>
      {children}
      <Toaster
        position="bottom-right"
        closeButton
        richColors
        toastOptions={{className: 'c-sonner-toast'}}
      />
    </NotifyContext.Provider>
  );
}
