import { forwardRef, type ButtonHTMLAttributes } from 'react';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg';
  asChild?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className = '', variant = 'primary', size = 'md', disabled, children, asChild, ...props }, ref) => {
    const baseClasses = 'inline-flex items-center justify-center font-medium rounded-lg transition-all duration-150 focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer select-none';
    
    const variants: Record<NonNullable<ButtonProps['variant']>, string> = {
      primary: 'bg-primary text-white hover:bg-primary-hover shadow-xs focus-visible:ring-primary',
      secondary: 'bg-secondary text-white hover:bg-slate-600 focus-visible:ring-secondary',
      outline: 'border border-border bg-surface text-text-primary hover:bg-surface-hover hover:text-primary hover:border-primary/50 focus-visible:ring-primary',
      ghost: 'text-text-secondary hover:text-text-primary hover:bg-surface-hover focus-visible:ring-primary',
      danger: 'bg-error text-white hover:bg-red-600 focus-visible:ring-error',
    };
    
    const sizes: Record<NonNullable<ButtonProps['size']>, string> = {
      sm: 'px-3 py-1.5 text-sm gap-1.5',
      md: 'px-4 py-2 text-base gap-2',
      lg: 'px-6 py-3 text-lg gap-2',
    };
    
    const Comp = asChild ? 'span' : 'button';
    
    return (
      <Comp
        ref={ref}
        className={`${baseClasses} ${variants[variant ?? 'primary']} ${sizes[size ?? 'md']} ${className}`}
        disabled={disabled}
        {...props}
      >
        {children}
      </Comp>
    );
  }
);

Button.displayName = 'Button';