{{- define "cs.fullname" -}}{{ .Release.Name }}-cronsentinel{{- end -}}
{{- define "cs.deployment" -}}
apiVersion: apps/v1
kind: Deployment
metadata: {name: {{ include "cs.fullname" .root }}-{{ .name }}, namespace: {{ .root.Release.Namespace }}}
spec:
  replicas: {{ .replicas }}
  selector: {matchLabels: {app: {{ include "cs.fullname" .root }}-{{ .name }}}}
  template:
    metadata: {labels: {app: {{ include "cs.fullname" .root }}-{{ .name }}}}
    spec:
      securityContext: {runAsNonRoot: true, seccompProfile: {type: RuntimeDefault}}
      containers:
        - name: {{ .name }}
          image: {{ .image }}
          {{- if .command }}
          command: {{ toJson .command }}
          {{- end }}
          envFrom: [{secretRef: {name: {{ include "cs.fullname" .root }}-env}}]
          {{- if .port }}
          ports: [{containerPort: {{ .port }}}]
          readinessProbe: {httpGet: {path: {{ .readinessPath | default "/readyz" | quote }}, port: {{ .port }}}, periodSeconds: 10, initialDelaySeconds: {{ .readinessInitialDelay | default 0 }}}
          livenessProbe: {httpGet: {path: {{ .livenessPath | default "/healthz" | quote }}, port: {{ .port }}}, periodSeconds: 20, initialDelaySeconds: {{ .livenessInitialDelay | default 0 }}}
          {{- end }}
          resources: {{ toYaml .resources | nindent 12 }}
{{- end -}}
