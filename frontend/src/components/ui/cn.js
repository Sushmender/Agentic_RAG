/**
 * src/components/ui/cn.js
 * Class name utility combining clsx + tailwind-merge
 */
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs) {
  return twMerge(clsx(inputs));
}
