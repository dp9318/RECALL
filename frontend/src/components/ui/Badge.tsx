import { forwardRef } from 'react';

export type BadgeVariant = 'default' | 'success' | 'warning' | 'error' | 'info' | 'outline' | 'primary';
export type BadgeSize = 'sm' | 'md' | 'lg';

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
  size?: BadgeSize;
}

const variants: Record<BadgeVariant, string> = {
  default: 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300',
  success: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  warning: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
  error: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  info: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  primary: 'bg-primary-light text-primary dark:bg-primary/20 dark:text-primary-light',
  outline: 'border-2 border-border text-text-secondary',
};

const sizes: Record<BadgeSize, string> = {
  sm: 'px-2 py-0.5 text-xs',
  md: 'px-2.5 py-1 text-sm',
  lg: 'px-3 py-1.5 text-base',
};

export const Badge = forwardRef<HTMLSpanElement, BadgeProps>(
  ({ className = '', variant = 'default', size = 'md', children, ...props }, ref) => {
    return (
      <span
        ref={ref}
        className={`
          inline-flex items-center font-medium rounded-full
          ${variants[variant]} ${sizes[size]} ${className}
        `}
        {...props}
      >
        {children}
      </span>
    );
  }
);

Badge.displayName = 'Badge';