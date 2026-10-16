/**
 * src/components/ui/Card.jsx
 * Card / Panel with header, body, footer slots
 */
import './Card.css';

export function Card({ className = '', children, hover = false, ...props }) {
  return (
    <div className={`card ${hover ? 'card--hover' : ''} ${className}`} {...props}>
      {children}
    </div>
  );
}

export function CardHeader({ className = '', children }) {
  return <div className={`card__header ${className}`}>{children}</div>;
}

export function CardBody({ className = '', children }) {
  return <div className={`card__body ${className}`}>{children}</div>;
}

export function CardFooter({ className = '', children }) {
  return <div className={`card__footer ${className}`}>{children}</div>;
}

export default Card;
