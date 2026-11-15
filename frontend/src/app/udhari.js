// Udhari (contract section 13, flag UDHARI): words shared by the Udhari screen and the Soundbox.

/** What to say when POST /tabs/{payer_id}/settle fails, by the contract's error codes. */
export function settleHint(e) {
  const reason = e?.details?.reason
  if (e?.code === 'INVALID_STATE' && reason === 'NOTHING_DUE') return 'Nothing is due on this tab any more, so nothing was taken off.'
  if (e?.code === 'INVALID_STATE' && reason === 'PAYMENT_ALREADY_USED') return 'This payment was already taken off the tab. Nothing new was written.'
  if (e?.code === 'INVALID_STATE') return 'Not possible for this payment right now.'
  if (e?.code === 'VALIDATION_ERROR') return 'This payment is not from this customer, so it can’t go on their tab.'
  if (e?.code === 'DUPLICATE_CONFLICT') return 'This request was already sent with different details. Reload and try again.'
  if (e?.code === 'NOT_FOUND') return 'This payment or tab is gone (was the demo reset?).'
  if (e?.code === 'UNREACHABLE') return 'Start the backend, then try again. A payment is never taken off twice.'
  return 'Try again. A payment is never taken off twice.'
}

/** A settle error that retrying can't fix (the tab or the payment is already done, or gone). */
export function settleFinal(e) {
  return ['INVALID_STATE', 'VALIDATION_ERROR', 'NOT_FOUND'].includes(e?.code)
}
