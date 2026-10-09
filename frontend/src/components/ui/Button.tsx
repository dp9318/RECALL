import { forwardRef, type ButtonHTMLAttributes } from 'react';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg';
  asChild?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className = '', variant = 'primary', size = 'md', disabled, children, asChild, ...props }, ref) => {
    const baseClasses = 'inline-flex items-center justify-center font-medium rounded-lg transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed';
    
    const variants: Record<NonNullable<ButtonProps['variant']>, string> = {
      primary: 'bg-primary text-white hover:bg-primary-hover focus:ring-primary',
      secondary: 'bg-secondary text-white hover:bg-slate-600 focus:ring-secondary',
      outline: 'border-2 border-primary text-primary hover:bg-primary-light focus:ring-primary',
      ghost: 'text-primary hover:bg-primary-light focus:ring-primary',
      danger: 'bg-error text-white hover:bg-red-600 focus:ring-error',
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