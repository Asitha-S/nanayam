// Which merchant the app screens show. Murugan (M001, Tamil) by default; Venkatesh (M002, Telugu) for the Telugu flow.
import { createContext, useContext, useMemo, useState } from 'react'
import { useApi } from '../api'

const KEY = 'naanayam.merchant'
const MerchantContext = createContext(null)

function readStored() {
  try {
    return window.localStorage.getItem(KEY) || 'M001'
  } catch {
    return 'M001'
  }
}

export function MerchantProvider({ children }) {
  const [merchantId, setMerchantIdState] = useState(readStored)
  const list = useApi('/merchants')
  const health = useApi('/health', { pollMs: 15000 })
  const setMerchantId = (id) => {
    setMerchantIdState(id)
    try {
      window.localStorage.setItem(KEY, id)
    } catch {
      /* private mode: the choice just isn't remembered */
    }
  }
  const value = useMemo(() => {
    const merchants = list.data?.merchants || []
    const merchant = merchants.find((m) => m.merchant_id === merchantId) || null
    return {
      merchantId,
      setMerchantId,
      merchants,
      merchant,
      language: merchant?.preferred_language || (merchantId === 'M002' ? 'te' : 'ta'),
      demoDate: health.data?.demo_date || null,
      health: health.data,
    }
  }, [merchantId, list.data, health.data])
  return <MerchantContext.Provider value={value}>{children}</MerchantContext.Provider>
}

/** { merchantId, setMerchantId, merchants, merchant, language, demoDate, health } */
export function useMerchant() {
  return useContext(MerchantContext)
}
