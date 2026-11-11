import {createContext, useCallback, useContext} from 'react';
import {useToast} from '@astryxdesign/core/Toast';

type Notify = (body: string, type?: 'info' | 'error') => void;
const NotifyContext = createContext<Notify>(() => undefined);

export function useNotify() {
  return useContext(NotifyContext);
}

export function NotifyProvider({children}: {children: React.ReactNode}) {
  const toast = useToast();
  const notify = useCallback<Notify>((body, type = 'info') => {
    toast({body, type});
  }, [toast]);
  return <NotifyContext.Provider value={notify}>{children}</NotifyContext.Provider>;
}
