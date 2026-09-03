import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

/** Standard Aceternity-style class-merging helper. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
