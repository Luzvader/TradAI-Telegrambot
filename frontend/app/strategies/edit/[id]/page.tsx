"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useParams } from "next/navigation";
import { CircularProgress, Typography, Button, TextField, Box } from "@mui/material";

export default function EditStrategyPage() {
  const router = useRouter();
  const params = useParams();
  const id = params?.id as string;
  const [strategy, setStrategy] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [fields, setFields] = useState<any>({});

  useEffect(() => {
    if (!id) return;
    fetch(`/api/strategies/${id}`)
      .then((r) => r.json())
      .then((data) => {
        setStrategy(data.strategy);
        setFields(data.strategy);
        setLoading(false);
      })
      .catch(() => {
        setError("No se pudo cargar la estrategia");
        setLoading(false);
      });
  }, [id]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFields({ ...fields, [e.target.name]: e.target.value });
  };

  const handleSave = async () => {
    await fetch(`/api/strategies`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...fields, id }),
    });
    router.push("/strategies");
  };

  if (loading) return <CircularProgress />;
  if (error) return <Typography color="error">{error}</Typography>;

  return (
    <Box sx={{ maxWidth: 500, mx: "auto", mt: 4 }}>
      <Typography variant="h5" gutterBottom>Edición avanzada de estrategia</Typography>
      {Object.keys(fields).map((key) => (
        <TextField
          key={key}
          name={key}
          label={key}
          value={fields[key] ?? ""}
          onChange={handleChange}
          fullWidth
          margin="normal"
        />
      ))}
      <Button variant="contained" color="primary" onClick={handleSave} sx={{ mt: 2 }}>
        Guardar cambios
      </Button>
    </Box>
  );
}
