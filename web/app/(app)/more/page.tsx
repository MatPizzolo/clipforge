import { Card, CardContent } from "@/components/ui/card";
import { COMING_SOON, NAV } from "@/components/nav";

export default function MorePage() {
  return (
    <Card>
      <CardContent className="divide-y">
        {NAV.filter((item) => !item.built).map((item) => (
          <div key={item.href} aria-disabled="true" className="flex items-center justify-between py-3">
            <span>{item.label}</span>
            <span className="text-xs text-muted-foreground">{COMING_SOON}</span>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
