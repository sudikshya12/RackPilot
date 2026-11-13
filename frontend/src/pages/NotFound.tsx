import { Link } from "react-router-dom";
import { Empty } from "@/components/ui/Primitives";

export function NotFound() {
  return <div className="panel"><Empty title="Page not found" action={<Link to="/" className="btn-primary">Back to overview</Link>}>The route does not exist in RackOps Lab.</Empty></div>;
}
