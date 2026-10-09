import { forwardRef } from 'react';

export const Card = forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className = '', children, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={`
          bg-surface rounded-xl border border-border shadow-sm
          ${className}
        `}
        {...props}
      >
        {children}
      </div>
    );
  }
);

Card.displayName = 'Card';

export const CardHeader = forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className = '', children, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={`
          px-6 py-4 border-b border-border
          ${className}
        `}
        {...props}
      >
        {children}
      </div>
    );
  }
);

CardHeader.displayName = 'CardHeader';

export const CardTitle = forwardRef<HTMLHeadingElement, React.HTMLAttributes<HTMLHeadingElement>>(
  ({ className = '', children, ...props }, ref) => {
    return (
      <h3
        ref={ref}
        className={`
          text-lg font-semibold text-text-primary
          ${className}
        `}
        {...props}
      >
        {children}
      </h3>
    );
  }
);

CardTitle.displayName = 'CardTitle';

export const CardDescription = forwardRef<HTMLParagraphElement, React.HTMLAttributes<HTMLParagraphElement>>(
  ({ className = '', children, ...props }, ref) => {
    return (
      <p
        ref={ref}
        className={`
          mt-1 text-sm text-text-secondary
          ${className}
        `}
        {...props}
      >
        {children}
      </p>
    );
  }
);

CardDescription.displayName = 'CardDescription';

export const CardContent = forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className = '', children, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={`
          px-6 py-4
          ${className}
        `}
        {...props}
      >
        {children}
      </div>
    );
  }
);

CardContent.displayName = 'CardContent';

export const CardFooter = forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className = '', children, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={`
          px-6 py-4 border-t border-border bg-gray-50 rounded-b-xl
          ${className}
        `}
        {...props}
      >
        {children}
      </div>
    );
  }
);

CardFooter.displayName = 'CardFooter';