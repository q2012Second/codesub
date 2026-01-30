import { useState, useEffect, useRef } from 'react';

/**
 * Returns a debounced version of the value.
 * Updates only after the specified delay with no new values.
 */
export function useDebouncedValue<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debounced;
}

/**
 * Returns a ref that tracks whether the component is still mounted.
 * Useful for preventing state updates after unmount.
 */
export function useMountedRef(): React.RefObject<boolean> {
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  return mounted;
}
