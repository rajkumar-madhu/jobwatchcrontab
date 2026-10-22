import { publicSpec } from "@/lib/api-reference";

export const dynamic = "force-static";

/** R69: the OpenAPI 3.1 description behind the reference, for code generators and API clients. */
export function GET() {
  return Response.json(publicSpec(), { headers: { "Content-Disposition": 'inline; filename="jobwatch-openapi.json"' } });
}
