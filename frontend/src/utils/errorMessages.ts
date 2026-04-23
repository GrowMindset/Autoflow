const normalizeWhitespace = (value: string): string => {
  return value.replace(/\s+/g, ' ').trim();
};

export const toUserFriendlyErrorMessage = (
  rawError: unknown,
  fallback = 'Something went wrong. Please try again.',
): string => {
  const raw = normalizeWhitespace(String(rawError ?? ''));
  if (!raw) return fallback;

  const lower = raw.toLowerCase();

  if (lower.includes("unsupported parameter: 'max_tokens'")) {
    return 'This model expects max completion tokens instead of max tokens. Please retry.';
  }
  if (
    lower.includes('invalid api key')
    || lower.includes('unauthorized')
    || lower.includes('status code: 401')
  ) {
    return 'Authentication failed. Reconnect your credential and try again.';
  }
  if (lower.includes('forbidden') || lower.includes('status code: 403')) {
    return 'Permission denied for this action. Check the account permissions.';
  }
  if (lower.includes('rate limit') || lower.includes('too many requests') || lower.includes('status code: 429')) {
    return 'Rate limit reached. Please wait a moment and retry.';
  }
  if (lower.includes('timed out') || lower.includes('timeout')) {
    return 'The request timed out. Please retry.';
  }
  if (lower.includes('could not resolve host')) {
    return 'Could not reach the target host. Check the URL/domain and try again.';
  }
  if (lower.includes('connection refused')) {
    return 'Could not connect to the target service. Verify it is reachable.';
  }
  if (lower.includes("loop safety cap reached for node")) {
    return 'Loop limit reached for a node. Increase loop limits or adjust loop conditions.';
  }
  if (lower.includes('workflow stopped due to loop safety cap')) {
    return 'Workflow stopped to prevent an infinite loop. Increase loop limits or adjust loop conditions.';
  }
  if (lower.includes('all incoming branches were blocked')) {
    return 'No branch produced data for this step.';
  }
  if (lower.includes('waiting for remaining unblocked inputs')) {
    return 'Waiting for other required branch inputs.';
  }

  return raw;
};
